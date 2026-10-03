"""Owned full-editor material capture. Never execute in the user's open editor.

Entry: pmx4ue.py material-preview. No animation required. Source assets are
read-only. v3 loads the installed daylight map without saving it; legacy v1/v2
must migrate before execution. A/B overrides are discarded on process exit.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import traceback
import unreal
from outline_contract import outline_spec, outline_assets, outline_args, verify_outline_receipt
from capture_retention import remove_native_duplicate

from material_preview_contract import validate, capture_jobs, png_evidence, require, verify_environment_review, CapturePixelsError
from ue_bridge import resolve, checked
from preview_framing import camera_spec, verify_framing
from head_hair_profile import validate_profile as validate_hair_profile
from ue_head_hair_binding import apply_binding


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def native(value):
    result = checked(value)
    require(result.get("ok") is True, "Native preview operation failed: " + str(result))
    return result


class Preview:
    def __init__(self):
        self.callback = None
        self.owned = False
        self.finished = False
        self.report = {"status": "failed", "captures": []}
        self.output = Path(os.environ["PMX4UE_OUTPUT"])
        require(not self.output.exists(), "Preview report exists; use a new output")

    def start(self):
        token = os.environ.get("PMX4UE_PREVIEW_TOKEN", "")
        command_line = unreal.SystemLibrary.get_command_line()
        require(re.fullmatch(r"[a-f0-9]{32}", token) and
                ("-PMX4UEPreview=" + token) in command_line, "Not an owned material-preview process")
        require("-RenderOffscreen" not in command_line, "Material review requires a visible editor viewport")
        self.owned = True
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        require(not self.level.is_in_play_in_editor(), "PIE must not be running")
        require(self.editor.get_editor_world().get_path_name().startswith(("/Temp/Untitled", "/Engine/Maps/Templates/")),
                "Refusing to replace a non-template editor world")
        config = read(os.environ["PMX4UE_CONFIG"])
        profile_path = Path(os.environ["PMX4UE_PREVIEW_PROFILE"])
        self.p = validate(read(profile_path), config["paths"]["ue_root"], config["pmx4ue"].get("material_source_mesh"))
        require(self.p["schema"] == "pmx4ue.material-preview.v3", "Migrate legacy preview to v3 subject-aware framing before execution")
        verify_environment_review(self.p)
        compile_report = read(Path(config["paths"]["artifact_dir"]) / "material_compile.json")
        require(compile_report.get("status") == "compiled_visual_pending", "Material compile gate not complete")
        self.project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
        require(self.project == Path(config["pmx4ue"]["project"]).resolve().parent, "Wrong project")
        self.api = resolve("visual")
        self.native_capture_dir = "MMD2UECaptures" if self.api.__name__.startswith("MMD2UE") else "PMX4UECaptures"
        for method in ("capture_visible_editor_viewport", "check_preview_texture_residency",
                       "frame_preview_subject",
                       "set_viewport_view_mode", "inspect_material_compile",
                       "set_character_outline_overlay", "set_character_depth_rim"):
            require(callable(getattr(self.api, method, None)), "Missing native Python method: " + method)
        self.mesh = unreal.load_asset(self.p["mesh"])
        require(isinstance(self.mesh, unreal.SkeletalMesh), "Missing skeletal mesh")
        self.materials = [m.get_editor_property("material_interface") for m in self.mesh.get_editor_property("materials")]
        require(self.materials and all(self.materials), "Empty material slot")
        self.hair_reports, self.hair_files = {}, {}
        for case in self.p["cases"]:
            if "head_hair_report" not in case:
                continue
            path = Path(case["head_hair_report"]).resolve()
            report = read(path)
            require(report.get("status") == "built_needs_runtime_visual_review" and
                    report.get("input_assets_unchanged") is True, "Head hair build did not pass")
            calibration = validate_hair_profile(report["profile"], config["paths"]["ue_root"])
            require(calibration["mesh"] == self.p["mesh"], "Head hair report targets another mesh")
            require(report.get("component_overrides"), "Head hair report has no material overrides")
            overrides = report["component_overrides"]
            require(len({r["index"] for r in overrides}) == len(overrides) and
                    {r["slot"] for r in overrides} == set(calibration["hair_slots"]), "Invalid hair slot receipt")
            for row in overrides:
                require(type(row["index"]) is int and 0 <= row["index"] < len(self.materials) and
                        str(self.mesh.get_editor_property("materials")[row["index"]].material_slot_name) == row["slot"],
                        "Head hair slot layout changed")
                require(row["material"].split('.')[0].startswith(config["paths"]["ue_root"] + '/'),
                        "Head hair material outside work order")
            by_index = {r["index"]: r["material"].split('.')[0] for r in overrides}
            for row in case["slots"]:
                if row["index"] in by_index and row.get("material"):
                    require(row["material"].split('.')[0] == by_index[row["index"]],
                            "Case material conflicts with head hair binding")
            self.hair_reports[case["name"]] = report
            self.hair_files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        providers = {r["profile"]["provider"] for r in self.hair_reports.values()}
        require(len(providers) <= 1, "Split preview runs using different runtime providers")
        self.hair_actor_class = None
        self.hair_driver = None
        if providers:
            class_name = "MMDFaceSDFPreviewActor" if next(iter(providers)) == "mmd2ue" else "PMX4UEFaceSDFPreviewActor"
            self.hair_actor_class = getattr(unreal, class_name, None)
            require(self.hair_actor_class is not None, "Missing compiled head hair preview actor: " + class_name)
        assets = [self.mesh.get_path_name()] + [m.get_path_name() for m in self.materials]
        hair_source_assets = []
        for report in self.hair_reports.values():
            assets += [r["material"] for r in report["component_overrides"]]
            hair_source_assets += list(report.get("input_hashes", {}))
        for case in self.p["cases"]:
            for row in case["slots"]:
                require(row["index"] < len(self.materials), "Slot outside mesh")
                if row.get("material"):
                    assets.append(row["material"])
            if "outline" in case:
                outline_spec(case["outline"], len(self.materials))
                assets += outline_assets(case["outline"])
            if "depth_rim" in case:
                assets.append(case["depth_rim"])
        if any("depth_rim" in c for c in self.p["cases"]):
            original = unreal.SystemLibrary.get_console_variable_int_value("r.CustomDepth")
            # This fresh process is owned by the preview; never save project settings.
            unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "r.CustomDepth 3")
            require(unreal.SystemLibrary.get_console_variable_int_value("r.CustomDepth") == 3,
                    "Could not enable stencil in the owned preview process; inspect API before continuing")
            self.report["custom_depth"] = dict(initial=original, preview=3, persistent_config_modified=False)
        # Compile actual baseline AND variant parents now; do not trust an older report alone.
        self.report["compile"] = {}
        for path in sorted(set(assets[1:])):
            material = unreal.load_asset(path)
            require(isinstance(material, unreal.MaterialInterface), "Invalid material: " + path)
            seen = set()
            while isinstance(material, unreal.MaterialInstance):
                require(material.get_path_name() not in seen, "Material parent cycle")
                seen.add(material.get_path_name())
                material = material.get_editor_property("parent")
            require(isinstance(material, unreal.Material), "Missing material parent")
            name = material.get_path_name()
            if name not in self.report["compile"]:
                self.report["compile"][name] = native(self.api.inspect_material_compile(name))
        self.inputs = self.dependencies(assets + hair_source_assets)
        for report in self.hair_reports.values():
            for asset, expected in report.get("input_hashes", {}).items():
                filename = str(self.project / "Content" / (asset.split('.')[0][len('/Game/'):] + ".uasset"))
                require(self.inputs["game_package_sha256"].get(filename) == expected,
                        "Head hair source changed since build: " + asset)
        self.report.update(schema="pmx4ue.material-captures.v1", profile=self.p,
                           profile_sha256=hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                           engine=unreal.SystemLibrary.get_engine_version(), provider=self.api.__name__,
                           rendering="owned_visible_editor_viewport", input_assets=self.inputs,
                           scope="Static material review only; no animation, physics or runtime SDF acceptance")
        self.report["head_hair_report_sha256"] = self.hair_files
        # v3 reviews the installed daylight map itself, only in this owned
        # process. No copied custom level and no save of the Engine template.
        self.daylight = self.p["schema"] in ("pmx4ue.material-preview.v2", "pmx4ue.material-preview.v3")
        self.direct_daylight = self.p["schema"] == "pmx4ue.material-preview.v3"
        if self.direct_daylight:
            template = self.p["environment"]["template"]
            self.daylight_file = Path(config["pmx4ue"]["engine"]) / "Engine/Content/Maps/Templates/OpenWorld.umap"
            require(self.daylight_file.is_file(), "Open World daylight map file is unavailable")
            self.daylight_sha256 = hashlib.sha256(self.daylight_file.read_bytes()).hexdigest()
            require(unreal.EditorAssetLibrary.does_asset_exist(template), "Open World daylight map is unavailable")
            require(self.level.load_level(template), "Could not load Open World daylight map")
            expected_world = template
            self.report["daylight_map"] = dict(path=template, source_sha256=self.daylight_sha256,
                                               saved_by_preview=False)
        else:
            require(not unreal.EditorAssetLibrary.does_asset_exist(self.p["level"]), "Preview map already exists")
            require(not (self.project / "Content" / (self.p["level"][len('/Game/'):] + ".umap")).exists(), "Preview map file exists")
        if self.daylight and not self.direct_daylight:
            template = self.p["environment"]["template"]
            require(unreal.EditorAssetLibrary.does_asset_exist(template), "Open World template unavailable; no empty-map fallback")
            require(self.level.new_level_from_template(self.p["level"], template), "Could not copy Open World template")
            expected_world = self.p["level"]
        elif not self.daylight:
            unreal.log_warning("Legacy v1 single-light preview: migrate to v2 Open World daylight for material review")
            require(self.level.new_level(self.p["level"]), "Could not create isolated preview level")
            expected_world = self.p["level"]
        world = self.editor.get_editor_world()
        require(world.get_path_name().split('.')[0] == expected_world, "Wrong daylight/editor world")
        # Record the actual render setting with each capture; do not change it
        # to mask a texture-streaming or mip-residency problem.
        self.actor = self.spawn(self.hair_actor_class or unreal.SkeletalMeshActor, "PMX4UE_MaterialReview")
        if self.daylight:
            self.actor.set_actor_location(unreal.Vector(*self.p["environment"]["model_location"]), False, False)
        self.body = self.actor.get_editor_property("skeletal_mesh_component")
        self.body.set_skeletal_mesh_asset(self.mesh)
        self.body.set_update_animation_in_editor(False)
        if self.hair_actor_class:
            self.hair_driver = self.actor.get_editor_property("face_sdf")
            self.hair_driver.set_editor_property("source_mesh", None)
            self.hair_driver.update_face_parameters()
        self.camera = self.spawn(unreal.CameraActor, "PMX4UE_ReviewCamera")
        self.setup_lighting()
        if self.p["exposure_ev100"] is not None:
            self.setup_fixed_exposure()
        self.report["environment"]["exposure"] = {
            "mode": "fixed_ev100" if self.p["exposure_ev100"] is not None else "template_project_defaults",
            "ev100": self.p["exposure_ev100"],
            "note": "Template/project exposure is allowed for Baseline and A/B. Auto exposure may adapt; matching policy does not guarantee identical effective exposure. No project settings changed."
        }
        self.jobs = capture_jobs(self.p)
        self.report["expected_captures"] = len(self.jobs)
        self.index, self.previous_case, self.phase = 0, None, "prepare"
        self.token = token
        self.deadline = time.monotonic() + len(self.jobs)*(self.p["warmup_seconds"]+70) + 120
        self.captures_dir = self.output.parent / ("captures_" + token)
        self.captures_dir.mkdir(parents=True, exist_ok=False)
        unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        self.callback = unreal.register_slate_post_tick_callback(self.tick)

    def setup_lighting(self):
        self.sky_components = []
        if self.daylight:
            actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
            suns = []
            for actor in actors:
                light = actor.get_component_by_class(unreal.DirectionalLightComponent)
                if light and light.get_editor_property("atmosphere_sun_light") and light.get_editor_property("atmosphere_sun_light_index") == 0:
                    suns.append((actor, light))
                sky = actor.get_component_by_class(unreal.SkyLightComponent)
                if sky:
                    self.sky_components.append(sky)
            require(len(suns) == 1 and self.sky_components and
                    any(isinstance(a, unreal.SkyAtmosphere) for a in actors),
                    "Open World lighting not loaded/unambiguous; inspect template/World Partition, do not substitute a single lamp")
            require(any(isinstance(a, unreal.LandscapeProxy) for a in actors),
                    "Open World landscape not loaded; load the preview region explicitly before capture")
            self.light, self.light_component = suns[0]
            require(self.light_component.get_editor_property("intensity") > 0 and
                    all(s.get_editor_property("intensity") > 0 for s in self.sky_components), "Inactive daylight illumination")
            self.report["environment"] = dict(
                template=self.p["environment"]["template"], model_location=self.p["environment"]["model_location"],
                sun=self.light.get_path_name(), sky_lights=[s.get_path_name() for s in self.sky_components],
                sky_intensities=[float(s.get_editor_property("intensity")) for s in self.sky_components],
                loaded_actors=[dict(path=a.get_path_name(), label=a.get_actor_label()) for a in actors])
        else:
            self.light = self.spawn(unreal.DirectionalLight, "PMX4UE_ReviewKey")
            self.light_component = self.light.get_component_by_class(unreal.DirectionalLightComponent)
            self.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
            self.light_component.set_editor_property("atmosphere_sun_light", True)
            self.light_component.set_editor_property("atmosphere_sun_light_index", 0)
            self.report["environment"] = {"mode": "legacy_single_light"}
        self.sun_rotation = self.light.get_actor_rotation()
        self.sun_intensity = float(self.light_component.get_editor_property("intensity"))
        self.report["environment"]["initial_sun"] = dict(pitch=self.sun_rotation.pitch, yaw=self.sun_rotation.yaw,
                                                         roll=self.sun_rotation.roll, intensity=self.sun_intensity)

    def setup_fixed_exposure(self):
        post = self.spawn(unreal.PostProcessVolume, "PMX4UE_ReviewExposure")
        post.set_editor_property("unbound", True)
        post.set_editor_property("priority", 10000.)
        require(unreal.SystemLibrary.get_console_variable_int_value("r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange") == 1,
                "EV100 profile requires extended luminance range; adapt exposure API explicitly, do not change project defaults")
        settings = post.get_editor_property("settings")
        for name, value in {"override_auto_exposure_min_brightness": True, "override_auto_exposure_max_brightness": True,
                            "auto_exposure_min_brightness": self.p["exposure_ev100"],
                            "auto_exposure_max_brightness": self.p["exposure_ev100"],
                            "override_auto_exposure_bias": True, "auto_exposure_bias": 0.0}.items():
            settings.set_editor_property(name, value)
        post.set_editor_property("settings", settings)

    def dependencies(self, paths):
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        registry.wait_for_completion()
        options = unreal.AssetRegistryDependencyOptions(include_soft_package_references=True, include_hard_package_references=True)
        pending, visited, hashes, external = list(paths), set(), {}, []
        while pending:
            package = str(pending.pop()).split('.')[0]
            if package in visited:
                continue
            visited.add(package)
            if not package.startswith("/Game/"):
                external.append(package)
                continue
            filename = self.project / "Content" / (package[len('/Game/'):] + ".uasset")
            require(filename.is_file(), "Save source/variant asset before preview: " + package)
            hashes[str(filename)] = hashlib.sha256(filename.read_bytes()).hexdigest()
            for suffix in (".uexp", ".ubulk"):
                sidecar = filename.with_suffix(suffix)
                if sidecar.exists():
                    hashes[str(sidecar)] = hashlib.sha256(sidecar.read_bytes()).hexdigest()
            pending += list(registry.get_dependencies(package, options) or [])
        return dict(game_package_sha256=hashes, external_packages=sorted(external),
                    note="Engine/plugin external packages listed, not hashed; retain engine/plugin revision in handoff")

    def spawn(self, cls, label):
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(cls, unreal.Vector(), unreal.Rotator())
        require(actor is not None, "Failed to spawn " + label)
        actor.set_actor_label(label)
        return actor

    def outline(self, spec, clear=False):
        result = native(self.api.set_character_outline_overlay(
            self.actor.get_actor_label(), *outline_args(spec, len(self.materials), clear)))
        verify_outline_receipt(spec, result, len(self.materials), clear)
        result["requested_routing"] = outline_spec(spec, len(self.materials))
        return result

    def rim(self, path, weight):
        return native(self.api.set_character_depth_rim(self.actor.get_actor_label(), path, 1, weight, False))

    def apply_case(self, case):
        if self.hair_driver:
            self.hair_driver.set_editor_property("source_mesh", None)
            self.hair_driver.update_face_parameters()
        if self.previous_case:
            if "outline" in self.previous_case:
                self.outline(self.previous_case["outline"], clear=True)
            if "depth_rim" in self.previous_case:
                self.rim(self.previous_case["depth_rim"], 0.)
        self.mids = []
        for i, material in enumerate(self.materials):
            self.body.set_material(i, material)
        for row in case["slots"]:
            material = unreal.load_asset(row["material"]) if row.get("material") else self.materials[row["index"]]
            self.body.set_material(row["index"], material)
        hair_report = self.hair_reports.get(case["name"])
        if hair_report:
            apply_binding(hair_report, self.body, self.hair_driver)
        for row in case["slots"]:
            if row.get("scalars"):
                material = self.body.get_material(row["index"])
                names = {str(n) for n in unreal.MaterialEditingLibrary.get_scalar_parameter_names(material)}
                require(set(row["scalars"]) <= names, "Unknown scalar parameter; inspect variant graph")
                mid = material if isinstance(material, unreal.MaterialInstanceDynamic) else self.body.create_dynamic_material_instance(row["index"], material)
                require(mid is not None, "Could not create transient material override")
                self.mids.append(mid)
                for name, value in row["scalars"].items():
                    mid.set_scalar_parameter_value(name, float(value))
        self.applied_effects = {}
        if hair_report:
            self.hair_driver.update_face_parameters()
            require(self.hair_driver.get_editor_property("hair_basis_valid"), "Head hair basis invalid in preview")
            receipt = dict(head_bone=hair_report["profile"]["head_bone"], materials=[])
            for row in hair_report["component_overrides"]:
                mid = self.body.get_material(row["index"])
                require(isinstance(mid, unreal.MaterialInstanceDynamic), "Head hair binding did not produce an MID")
                # MaterialEditingLibrary getter only accepts Constant instances.
                # MID's ScriptName=GetScalarParameterValue reads the live override.
                valid = float(mid.get_scalar_parameter_value("HairBasisRuntimeValid"))
                require(valid > .99, "Hair preview still using fallback")
                receipt["materials"].append(dict(index=row["index"], active=valid,
                    parent=mid.get_editor_property("parent").get_path_name(),
                    highlight_strength=float(mid.get_scalar_parameter_value("HairHighlightStrength"))))
            receipt["center_ws"] = str(self.hair_driver.get_editor_property("hair_sphere_center_world"))
            receipt["up_ws"] = str(self.hair_driver.get_editor_property("hair_up_world"))
            self.applied_effects["head_hair"] = receipt
        if "outline" in case:
            self.applied_effects["outline"] = self.outline(case["outline"])
        if "depth_rim" in case:
            self.applied_effects["depth_rim"] = self.rim(case["depth_rim"], 1.)
        self.previous_case = case

    def tick(self, _delta):
        try:
            now = time.monotonic()
            require(now < self.deadline, "Preview timeout")
            if self.phase == "prepare":
                if self.index == len(self.jobs):
                    self.finish()
                    return
                case, camera, light, mode = self.jobs[self.index]
                if case != self.previous_case:
                    self.apply_case(case)
                rotation = (unreal.Rotator(pitch=light.get("pitch", self.sun_rotation.pitch),
                            yaw=light.get("yaw", self.sun_rotation.yaw + light.get("yaw_offset", 0.)), roll=self.sun_rotation.roll)
                            if self.daylight else unreal.Rotator(pitch=light["pitch"], yaw=light["yaw"], roll=0.))
                self.light.set_actor_rotation(rotation, False)
                self.light_component.set_intensity(light.get("intensity", self.sun_intensity))
                for sky in self.sky_components:
                    sky.recapture_sky()
                require(self.direct_daylight, "Subject-aware screenshots require a migrated v3 profile")
                self.camera_json = json.dumps(camera_spec(camera))
                aligned = native(self.api.frame_preview_subject(self.actor.get_actor_label(), self.camera_json, True))
                native(self.api.set_viewport_view_mode(mode))
                unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
                # Never save the Engine daylight template. Legacy copied-map
                # profiles retain their old baseline-only behavior.
                if self.index == 0 and not self.direct_daylight:
                    require(self.level.save_current_level(), "Could not save baseline preview map")
                actual_rotation = self.light.get_actor_rotation()
                require(all(abs((getattr(actual_rotation, axis) - getattr(rotation, axis) + 180.) % 360. - 180.) < .1
                            for axis in ("pitch", "yaw", "roll")), "Sun rotation readback differs from requested rotation")
                self.row = dict(case=case["name"], camera=camera, light=light, mode=mode, aligned=aligned,
                                scene_effects=self.applied_effects,
                                actual_sun=dict(pitch=actual_rotation.pitch, yaw=actual_rotation.yaw,
                                                roll=actual_rotation.roll, intensity=float(self.light_component.get_editor_property("intensity"))))
                self.phase, self.since = "warmup", time.monotonic()
            elif self.phase == "warmup":
                residency = native(self.api.check_preview_texture_residency(self.actor.get_actor_label(), 60.0))
                self.row["texture_residency"] = residency
                require(now-self.since < 60,
                        f"Character textures did not finish loading: {residency['pending']} pending; inspect texture paths/mips")
                if now-self.since >= self.p["warmup_seconds"] and residency["ready"]:
                    name = f"PMX4UE_{self.token}_{self.index:04d}.png"
                    response = json.loads(self.api.capture_visible_editor_viewport(name, self.actor.get_actor_label(), self.camera_json))
                    # A viewport resize/camera transition can invalidate the fit during warmup.
                    # Retry only a geometric framing failure, never missing/hidden subjects.
                    if response.get("ok") is False and response.get("schema") == "pmx4ue.subject-frame.v1":
                        retries = self.row.setdefault("framing_retries", [])
                        require(len(retries) < 2, "Viewport framing kept changing; stop interaction and rerun: " + str(response))
                        retries.append(response)
                        self.row["aligned"] = native(self.api.frame_preview_subject(self.actor.get_actor_label(), self.camera_json, True))
                        self.since = time.monotonic()
                        return
                    require(response.get("ok") is True, "Native capture failed: " + str(response))
                    require(response.get("source") == "visible_viewport_backbuffer", "Unexpected screenshot source")
                    width, height = response["width"], response["height"]
                    self.row.update(capture_source=response["source"], viewport_width=width, viewport_height=height,
                                    alpha_policy=response.get("alpha_policy", "legacy_unreported"),
                                    r_screen_percentage_setting=response["r_screen_percentage_setting"])
                    self.row["framing"] = response["framing"]
                    verify_framing(self.row, self.p["mesh"])
                    self.pending = Path(unreal.Paths.convert_relative_path_to_full(response["output_path"])).resolve()
                    require(self.pending.parent == (self.project / "Saved" / self.native_capture_dir).resolve() and self.pending.name == name,
                            "Unexpected capture output path")
                    self.capture_error = "Screenshot file not yet observed"
                    self.phase, self.since = "capture", now
            elif self.phase == "capture":
                require(now-self.since < 60, f"Screenshot did not finish within 60 seconds: {self.pending}: {self.capture_error}")
                try:
                    png_evidence(self.pending, self.row["viewport_width"], self.row["viewport_height"])
                except CapturePixelsError as error:
                    self.report["invalid_capture"] = {"path": str(self.pending), "error": str(error)}
                    raise  # A complete PNG with broken alpha/encoding will not improve by waiting.
                except (OSError, ValueError) as error:
                    self.capture_error = str(error)
                    return  # Preserve polling for filesystem/PNG completion.
                destination = self.captures_dir / self.pending.name
                with destination.open("xb") as stream:
                    stream.write(self.pending.read_bytes())
                self.row["image"] = png_evidence(destination, self.row["viewport_width"], self.row["viewport_height"])
                self.report["captures"].append(self.row)
                self.persist()
                self.row["native_copy_retention"] = remove_native_duplicate(
                    self.project, self.pending, destination, self.token, self.row["image"]["sha256"])
                self.persist()
                self.index += 1
                self.phase = "prepare"
        except Exception:
            self.finish(traceback.format_exc())

    def persist(self):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")

    def finish(self, error=None):
        if self.finished:
            return
        self.finished = True
        if self.callback is not None:
            unreal.unregister_slate_post_tick_callback(self.callback)
            self.callback = None
        unchanged = False
        try:
            if hasattr(self, "inputs"):
                unchanged = all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == value
                                for p, value in self.inputs["game_package_sha256"].items())
                unchanged = unchanged and all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == value
                                             for p, value in self.hair_files.items())
        except OSError:
            error = (error or "") + traceback.format_exc()
        if hasattr(self, "daylight_file"):
            try:
                daylight_unchanged = (self.daylight_file.is_file() and
                                      hashlib.sha256(self.daylight_file.read_bytes()).hexdigest() == self.daylight_sha256)
            except OSError:
                daylight_unchanged = False
                error = (error or "") + traceback.format_exc()
            self.report.setdefault("daylight_map", {})["source_unchanged"] = daylight_unchanged
            if not daylight_unchanged:
                error = (error or "") + " Open World source map changed during preview"
        self.report.update(status="failed" if error or not unchanged else "captured_visual_pending",
                           input_assets_unchanged=unchanged, visual_accepted=False)
        if error:
            self.report["error"] = error
        try:
            self.persist()
        finally:
            if self.owned and hasattr(self, "editor"):
                unreal.EditorPythonScripting.set_keep_python_script_alive(False)
                unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")


if __name__ == "__main__":
    preview = Preview()
    try:
        preview.start()
    except Exception:
        preview.finish(traceback.format_exc())
        raise
