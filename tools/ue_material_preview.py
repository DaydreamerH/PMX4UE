"""Owned full-editor material capture. Never execute in the user's open editor.

Entry: pmx4ue.py material-preview. No animation required. Source assets are
read-only; only the new baseline preview map is saved. A/B overrides live on
the preview component and are discarded when this owned process quits.
"""
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import time
import traceback
import unreal

from material_preview_contract import validate, png_evidence, require
from ue_bridge import resolve, checked


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
        self.owned = True
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        require(not self.level.is_in_play_in_editor(), "PIE must not be running")
        require(self.editor.get_editor_world().get_path_name().startswith(("/Temp/Untitled", "/Engine/Maps/Templates/")),
                "Refusing to replace a non-template editor world")
        config = read(os.environ["PMX4UE_CONFIG"])
        profile_path = Path(os.environ["PMX4UE_PREVIEW_PROFILE"])
        self.p = validate(read(profile_path), config["paths"]["ue_root"], config["pmx4ue"].get("material_source_mesh"))
        compile_report = read(Path(config["paths"]["artifact_dir"]) / "material_compile.json")
        require(compile_report.get("status") == "compiled_visual_pending", "Material compile gate not complete")
        self.project = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
        require(self.project == Path(config["pmx4ue"]["project"]).resolve().parent, "Wrong project")
        self.api = resolve("visual")
        self.native_capture_dir = "MMD2UECaptures" if self.api.__name__.startswith("MMD2UE") else "PMX4UECaptures"
        for method in ("capture_editor_viewport", "set_viewport_view_mode", "inspect_material_compile",
                       "set_character_outline_overlay", "set_character_depth_rim"):
            require(callable(getattr(self.api, method, None)), "Missing native Python method: " + method)
        self.mesh = unreal.load_asset(self.p["mesh"])
        require(isinstance(self.mesh, unreal.SkeletalMesh), "Missing skeletal mesh")
        self.materials = [m.get_editor_property("material_interface") for m in self.mesh.get_editor_property("materials")]
        require(self.materials and all(self.materials), "Empty material slot")
        assets = [self.mesh.get_path_name()] + [m.get_path_name() for m in self.materials]
        for case in self.p["cases"]:
            for row in case["slots"]:
                require(row["index"] < len(self.materials), "Slot outside mesh")
                if row.get("material"):
                    assets.append(row["material"])
            assets += [case[k] for k in ("outline", "depth_rim") if k in case]
        if any("depth_rim" in c for c in self.p["cases"]):
            require(unreal.SystemLibrary.get_console_variable_int_value("r.CustomDepth") == 3,
                    "Depth rim requires stencil (r.CustomDepth=3); review project settings separately")
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
        self.inputs = self.dependencies(assets)
        self.report.update(schema="pmx4ue.material-captures.v1", profile=self.p,
                           profile_sha256=hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                           engine=unreal.SystemLibrary.get_engine_version(), provider=self.api.__name__,
                           rendering="owned_offscreen_editor", input_assets=self.inputs,
                           scope="Static material review only; no animation, physics or runtime SDF acceptance")
        require(not unreal.EditorAssetLibrary.does_asset_exist(self.p["level"]), "Preview map already exists")
        require(not (self.project / "Content" / (self.p["level"][len('/Game/'):] + ".umap")).exists(), "Preview map file exists")
        # No actor removal and no SaveDirtyPackages. new_level only in this owned template process.
        require(self.level.new_level(self.p["level"]), "Could not create isolated preview level")
        world = self.editor.get_editor_world()
        require(world.get_path_name().split('.')[0] == self.p["level"], "Wrong isolated world")
        self.actor = self.spawn(unreal.SkeletalMeshActor, "PMX4UE_MaterialReview")
        self.body = self.actor.get_editor_property("skeletal_mesh_component")
        self.body.set_skeletal_mesh_asset(self.mesh)
        self.body.set_update_animation_in_editor(False)
        self.camera = self.spawn(unreal.CameraActor, "PMX4UE_ReviewCamera")
        self.light = self.spawn(unreal.DirectionalLight, "PMX4UE_ReviewKey")
        self.light_component = self.light.get_component_by_class(unreal.DirectionalLightComponent)
        self.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
        # Existing stylized graphs query atmosphere light 0; a generic lamp
        # without this registration would not exercise their authored lobes.
        self.light_component.set_editor_property("atmosphere_sun_light", True)
        self.light_component.set_editor_property("atmosphere_sun_light_index", 0)
        post = self.spawn(unreal.PostProcessVolume, "PMX4UE_ReviewExposure")
        post.set_editor_property("unbound", True)
        require(unreal.SystemLibrary.get_console_variable_int_value("r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange") == 1,
                "EV100 profile requires extended luminance range; adapt exposure API explicitly, do not change project defaults")
        settings = post.get_editor_property("settings")
        for name, value in {"override_auto_exposure_min_brightness": True, "override_auto_exposure_max_brightness": True,
                            "auto_exposure_min_brightness": self.p["exposure_ev100"],
                            "auto_exposure_max_brightness": self.p["exposure_ev100"],
                            "override_auto_exposure_bias": True, "auto_exposure_bias": 0.0}.items():
            settings.set_editor_property(name, value)
        post.set_editor_property("settings", settings)
        self.jobs = list(itertools.product(self.p["cases"], self.p["cameras"], self.p["lights"], self.p["modes"]))
        self.report["expected_captures"] = len(self.jobs)
        self.index, self.previous_case, self.phase = 0, None, "prepare"
        self.token = token
        self.deadline = time.monotonic() + len(self.jobs)*(self.p["warmup_seconds"]+70) + 120
        self.captures_dir = self.output.parent / ("captures_" + token)
        self.captures_dir.mkdir(parents=True, exist_ok=False)
        unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        self.callback = unreal.register_slate_post_tick_callback(self.tick)

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

    def outline(self, path, excluded=""):
        native(self.api.set_character_outline_overlay(self.actor.get_actor_label(), path, "", "", excluded, "", "", 6000., False))

    def rim(self, path, weight):
        native(self.api.set_character_depth_rim(self.actor.get_actor_label(), path, 1, weight, False))

    def apply_case(self, case):
        if self.previous_case:
            if "outline" in self.previous_case:
                self.outline(self.previous_case["outline"], ",".join(map(str, range(len(self.materials)))))
            if "depth_rim" in self.previous_case:
                self.rim(self.previous_case["depth_rim"], 0.)
        self.mids = []
        for i, material in enumerate(self.materials):
            self.body.set_material(i, material)
        for row in case["slots"]:
            material = unreal.load_asset(row["material"]) if row.get("material") else self.materials[row["index"]]
            self.body.set_material(row["index"], material)
            if row.get("scalars"):
                names = {str(n) for n in unreal.MaterialEditingLibrary.get_scalar_parameter_names(material)}
                require(set(row["scalars"]) <= names, "Unknown scalar parameter; inspect variant graph")
                mid = self.body.create_dynamic_material_instance(row["index"], material)
                require(mid is not None, "Could not create transient material override")
                self.mids.append(mid)
                for name, value in row["scalars"].items():
                    mid.set_scalar_parameter_value(name, float(value))
        if "outline" in case:
            self.outline(case["outline"])
        if "depth_rim" in case:
            self.rim(case["depth_rim"], 1.)
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
                self.light.set_actor_rotation(unreal.Rotator(light["pitch"], light["yaw"], 0.), False)
                self.light_component.set_intensity(light["intensity"])
                aligned = native(self.api.align_viewport_to_camera(self.camera.get_actor_label(), camera["azimuth"],
                                 camera["distance"], camera["height"], camera["fov"], self.actor.get_actor_label()))
                native(self.api.set_viewport_view_mode(mode))
                unreal.AutomationUtilsBlueprintLibrary.finish_all_asset_compilation()
                # Save only a reusable baseline map, before any experimental overrides.
                if self.index == 0:
                    require(self.level.save_current_level(), "Could not save baseline preview map")
                self.row = dict(case=case["name"], camera=camera, light=light, mode=mode, aligned=aligned)
                self.phase, self.since = "warmup", time.monotonic()
            elif self.phase == "warmup" and now-self.since >= self.p["warmup_seconds"]:
                name = f"PMX4UE_{self.token}_{self.index:04d}.png"
                response = native(self.api.capture_editor_viewport(name, self.p["width"], self.p["height"]))
                self.pending = Path(unreal.Paths.convert_relative_path_to_full(response["output_path"])).resolve()
                require(self.pending.parent == (self.project / "Saved" / self.native_capture_dir).resolve() and self.pending.name == name,
                        "Unexpected capture output path")
                self.capture_error = "Screenshot file not yet observed"
                self.phase, self.since = "capture", now
            elif self.phase == "capture":
                require(now-self.since < 60, f"Screenshot did not finish within 60 seconds: {self.pending}: {self.capture_error}")
                try:
                    png_evidence(self.pending, self.p["width"], self.p["height"])
                except (OSError, ValueError) as error:
                    self.capture_error = str(error)
                    return  # HighResShot is asynchronous; partial file is not completion.
                destination = self.captures_dir / self.pending.name
                with destination.open("xb") as stream:
                    stream.write(self.pending.read_bytes())
                self.row["image"] = png_evidence(destination, self.p["width"], self.p["height"])
                self.report["captures"].append(self.row)
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
        except OSError:
            error = (error or "") + traceback.format_exc()
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


preview = Preview()
try:
    preview.start()
except Exception:
    preview.finish(traceback.format_exc())
    raise
