"""Portable agent workbench. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
LEGACY = ROOT / "tools/legacy"
sys.path.insert(0, str(LEGACY))
from mmd2ue_core import make_character_config, build_source_audit, build_material_map_draft

STAGES = ("audit", "capabilities", "export", "skeleton-audit", "skeleton-review", "skeleton-plan", "skeleton-apply",
          "material-draft", "material-check", "ue-build", "ue-validate", "material-compile", "ik", "retarget-pose", "animation-export",
          "physics-inventory", "physics-inspect", "physics-plan", "physics-build",
          "physics-test", "performance")
STAGES += ("face-sdf", "material-preview", "material-build", "material-preflight", "delivery-check", "scene-effects-build")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    with Path(path).open("rb") as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(path):
    path = Path(path).resolve()
    c = read(path)
    require(c.get("pmx4ue", {}).get("version") == 1, "Not a PMX4UE v1 work order")
    project = Path(c["pmx4ue"]["project"]).resolve()
    require(project.suffix == ".uproject" and project.is_file(), "Target .uproject is missing")
    require(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]+", c["character"]["id"]), "Invalid character id")
    require(math.isfinite(c["source"]["scale"]) and c["source"]["scale"] > 0, "Invalid meters/PMX-unit scale")
    expected = f"/Game/PMX4UE/{c['character']['id']}/{c['pmx4ue']['variant']}"
    require(re.fullmatch(r"/Game/PMX4UE/[A-Za-z0-9_/]+", expected), "Invalid variant")
    require(c["paths"]["ue_root"] == expected, "UE namespace must match this character/variant")
    return c, project, Path(c["paths"]["artifact_dir"]).resolve()


def initialize(args):
    project, pmx = Path(args.project).resolve(), Path(args.pmx).resolve()
    require(project.is_file() and project.suffix == ".uproject", "Provide an existing .uproject")
    require(pmx.is_file() and pmx.suffix.lower() == ".pmx", "Provide an existing PMX")
    require(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", args.variant), "Invalid variant")
    require(math.isfinite(args.scale) and args.scale > 0, "Scale must be positive meters per PMX unit")
    dest = Path(args.output).resolve()
    require(not dest.exists(), "Work order already exists; choose another output")
    artifact = project.parent / "Saved/PMX4UE" / args.id / args.variant
    source_root = Path(args.source_root).resolve() if args.source_root else pmx.parent
    require(pmx.is_relative_to(source_root), "PMX must be inside source root")
    c = make_character_config(project.parent, args.id, args.id, pmx, source_root, args.scale)
    c["source"].update(pmx=str(pmx), root=str(source_root))
    c["paths"].update(artifact_dir=str(artifact), material_map=str(artifact / "material_map.json"),
                      ue_root=f"/Game/PMX4UE/{args.id}/{args.variant}")
    c["notes"] = ["Agent-owned work order; see PMX4UE/AGENTS.md. Source assets remain read-only."]
    c["features"] = {}  # Optional effects must be selected after material/UV review.
    c["skeleton"] = dict(goal="clean_ue_fk", shoulder_strategy="branch_helpers", roles={})
    c["pmx4ue"] = dict(version=1, project=str(project), variant=args.variant,
                       blender=args.blender or "", engine=args.engine or "",
                       source_scale_reviewed=False, skeleton_policy="preserve",
                       skeleton_reviewed=False, material_reviewed=False,
                       skeleton_decision=str(artifact / "skeleton_decision.json"),
                       rig_profile=str(dest.parent / "rig.json"),
                       retarget_pose_profile=str(dest.parent / "retarget_pose.json"),
                       animation_export_profile=str(dest.parent / "animation_export.json"),
                       material_preview_profile=str(dest.parent / "material_preview.json"),
                       material_preview_run="v1",
                       physics_profile=str(dest.parent / "physics.json"))
    write(dest, c)
    return {"config": str(dest), "next": "doctor, then audit; review source scale before export"}


def doctor(c, project):
    p = c["pmx4ue"]
    engine = Path(p["engine"])
    checks = {"project": project.is_file(), "pmx": Path(c["source"]["pmx"]).is_file(),
              "blender": Path(p["blender"]).is_file(),
              "ue_editor": (engine / "Engine/Binaries/Win64/UnrealEditor-Cmd.exe").is_file(),
              "native_source": ((project.parent / "Plugins/PMX4UE/PMX4UE.uplugin").is_file()
                                or (project.parent / "Source/MMD2UEEditor/MMD2UEEditor.Build.cs").is_file())}
    return {"paths_ok": all(checks.values()), "checks": checks,
            "unverified": ["Blender mmd_tools addon", "C++ toolchain and compiled plugin load", "UE APIs for this engine version"],
            "note": "Path checks are not a successful import or runtime validation."}


@contextlib.contextmanager
def project_lock(project):
    path = project.parent / "Saved/PMX4UE/.agent.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "time": time.time()}))
    except FileExistsError:
        raise ValueError(f"Another workflow owns {path}; inspect stale locks manually")
    try:
        yield
    finally:
        path.unlink()


def install_plugin(project, apply=False, source=None):
    require(not (project.parent / "Source/MMD2UEEditor/MMD2UEEditor.Build.cs").is_file(),
            "MMD2UE already provides native nodes; do not install a duplicate plugin")
    src = Path(source).resolve() if source else ROOT / "unreal/PMX4UE"
    dest = project.parent / "Plugins/PMX4UE"
    require((src / "PMX4UE.uplugin").is_file(), "Plugin source/packaged directory missing")
    require(not dest.exists(), "Destination exists; compare/version it instead of overwriting")
    if apply:
        with project_lock(project):
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns("Intermediate", ".git"))
    return {"source": str(src), "destination": str(dest), "copied": apply,
            "note": "Source-only plugins require compilation; .uproject is not modified."}


def recipe(c, project, a, stage):
    """Return auditable argv/env/input/output contract without performing the stage."""
    p = c["pmx4ue"]
    config = a / "resolved_config.json"
    base_blend = a / (c["character"]["id"] + ".blend")
    base_fbx = a / (c["character"]["id"] + ".fbx")
    profile = Path(p["physics_profile"])
    out = a / (stage.replace("-", "_") + ".json")
    env = {}
    inputs, outputs = [], [out]
    argv = []
    internal = None

    def py(script, *args):
        return [sys.executable, str(LEGACY / script), *map(str, args)]

    def blender(script, *args, blend=None):
        return [p["blender"], "--background", *([str(blend)] if blend else []),
                "--python-exit-code", "1", "--python", str(script), "--", *map(str, args)]

    def ue(script, pie=False, visible=False):
        exe = Path(p["engine"]) / "Engine/Binaries/Win64" / ("UnrealEditor.exe" if pie else "UnrealEditor-Cmd.exe")
        env.update(PMX4UE_SCRIPT=str(script), PMX4UE_CONFIG=str(config), PMX4UE_STAGE=stage,
                   MMD2UE_CHARACTER_CONFIG=str(config), MMD2UE_BUILD_MODE="build", MMD2UE_ASSET_VARIANT="")
        flag = "-ExecutePythonScript=" if pie else "-script="
        return [str(exe), str(project), *(["/Engine/Maps/Templates/Template_Default", *([] if visible else ["-RenderOffscreen"]),
                "-ini:EditorSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False"] if pie else ["-run=pythonscript"]),
                flag + str(ROOT / "tools/ue_entry.py"), "-unattended", "-nop4", "-nosplash"]

    if stage == "delivery-check":
        require(p.get("delivery_profile"), "Set delivery_profile to the reviewed asset/effect manifest")
        internal = "delivery"
        inputs = [Path(p["delivery_profile"])]
    elif stage == "material-preflight":
        env.update(PMX4UE_OUTPUT=str(out))
        argv = ue(ROOT / "tools/ue_material_preflight.py") + ["-AllowCommandletRendering"]
    elif stage == "material-preview":
        require(p.get("material_preview_profile"), "Set material_preview_profile after visual test planning")
        run_name = p.get("material_preview_run", "v1")
        require(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", run_name), "Invalid material_preview_run")
        out = a / "material_previews" / run_name / "material_preview.json"
        outputs = [out]
        inputs = [Path(p["material_preview_profile"]), a / "material_compile.json"]
        token = uuid.uuid4().hex
        env.update(PMX4UE_PREVIEW_PROFILE=str(inputs[0]), PMX4UE_OUTPUT=str(out), PMX4UE_PREVIEW_TOKEN=token)
        argv = ue(ROOT / "tools/ue_material_preview.py", pie=True, visible=True) + ["-PMX4UEPreview=" + token]
    elif stage == "face-sdf":
        require(p.get("face_sdf_profile"), "Set face_sdf_profile after face-axis review")
        inputs = [Path(p["face_sdf_profile"])]
        env.update(PMX4UE_FACE_SDF_PROFILE=str(inputs[0]), PMX4UE_OUTPUT=str(out))
        argv = ue(ROOT / "tools/ue_face_sdf_workflow.py") + ["-AllowCommandletRendering"]
    elif stage == "audit":
        internal = "audit"
        inputs = [Path(c["source"]["pmx"])]
    elif stage == "capabilities":
        env.update(PMX4UE_OUTPUT=str(out))
        argv = ue(ROOT / "tools/ue_capabilities.py")
    elif stage == "animation-export":
        require(p.get("animation_export_profile"), "Set animation_export_profile first")
        inputs = [Path(p["animation_export_profile"])]
        env.update(PMX4UE_ANIMATION_PROFILE=str(inputs[0]), PMX4UE_OUTPUT=str(out))
        argv = ue(ROOT / "tools/ue_animation_export.py")
    elif stage == "material-compile":
        inputs = [a / "ue_validation.json"]
        env.update(PMX4UE_OUTPUT=str(out))
        argv = ue(ROOT / "tools/ue_material_compile.py") + ["-AllowCommandletRendering"]
    elif stage == "export":
        require(p.get("source_scale_reviewed") is True, "Review source scale (meters per PMX unit) first")
        inputs = [Path(c["source"]["pmx"])]
        outputs = [base_blend, base_fbx, a / "blender_manifest.json", base_fbx.with_name(base_fbx.stem+'.raw.fbx')]
        argv = blender(ROOT / "tools/blender_prepare.py", "--pmx", inputs[0], "--source-root", c["source"]["root"],
                       "--out-dir", a, "--character-id", c["character"]["id"], "--scale", c["source"]["scale"], "--fbx-units", "cm-native")
    elif stage == "skeleton-audit":
        inputs = [base_blend]
        argv = blender(LEGACY / "blender_skeleton_audit.py", out, blend=base_blend)
    elif stage == "skeleton-review":
        require(c.get("skeleton", {}).get("roles"), "Map actual torso/left/right upper-limb roles first")
        inputs = [a / "skeleton_audit.json"]
        argv = py("skeleton_review.py", "--audit", inputs[0], "--config", config, "--output", out)
    elif stage in ("skeleton-plan", "skeleton-apply"):
        require(p.get("skeleton_reviewed") is True and p["skeleton_policy"] == "upper-only", "Review an upper-only skeleton plan, or use preserve")
        require(c.get("skeleton", {}).get("roles"), "Explicit reviewed left/right roles required")
        if stage == "skeleton-plan":
            inputs = [a / "skeleton_audit.json"]
            argv = py("skeleton_plan.py", "--audit", inputs[0], "--config", config, "--output", out)
        else:
            inputs = [base_blend, a / "skeleton_plan.json"]
            outputs += [a / "upper_only.blend", a / "upper_only.fbx"]
            argv = blender(LEGACY / "blender_apply_skeleton_plan.py", "--plan", inputs[1], "--out-blend", outputs[1],
                           "--out-fbx", outputs[2], "--report", out, "--cm-native", blend=base_blend)
    elif stage == "material-draft":
        internal = "draft"
        inputs = [a / "blender_manifest.json"]
        outputs = [Path(c["paths"]["material_map"])]
    elif stage == "material-check":
        inputs = [Path(c["paths"]["material_map"]), a / "blender_manifest.json"]
        outputs = []
        argv = [sys.executable, str(LEGACY / "mmd2ue.py"), "--project-root", str(project.parent), "check-map", "--config", str(config)]
    elif stage == "scene-effects-build":
        require(p.get("material_reviewed") is True, "Review materials before scene effects")
        require(any((c.get("features", {}).get(k) or {}).get("mode") == "enabled" for k in ("outline", "depth_rim")),
                "Explicitly enable at least one reviewed outline/depth_rim candidate")
        inputs = [Path(c["paths"]["material_map"]), a / "blender_manifest.json", a / "material_compile.json"]
        env.update(PMX4UE_OUTPUT=str(out))
        argv = ue(ROOT / "tools/ue_scene_effects.py") + ["-AllowCommandletRendering"]
    elif stage in ("ue-build", "material-build", "ue-validate"):
        require(p.get("material_reviewed") is True, "Agent must review material slots/textures first")
        require(p["skeleton_policy"] in ("preserve", "upper-only"), "Unsupported skeleton policy; extend adapter explicitly")
        inputs = [Path(c["paths"]["material_map"]), a / "blender_manifest.json"]
        if not p.get("material_source_mesh"):
            inputs.insert(0, Path(c["paths"].get("fbx", base_fbx)))
        if p["skeleton_policy"] == "upper-only" and not p.get("material_source_mesh"):
            inputs += [a / "skeleton_apply.json"]
        outputs = [a / ("ue_validation.json" if stage == "ue-validate" else "ue_build_report.json")]
        argv = ue(LEGACY / ("ue_validate.py" if stage == "ue-validate" else "ue_build_character.py"))
        if stage == "material-build":
            require(p.get("material_source_mesh"), "Set material_source_mesh to the retained mesh")
            require(not p["material_source_mesh"].startswith(c["paths"]["ue_root"] + "/"), "Use a new variant separate from the retained mesh")
            env["MMD2UE_BUILD_MODE"] = "material"
    elif stage == "ik":
        inputs = [Path(p["rig_profile"])]
        env.update(PMX4UE_RIG_PROFILE=str(inputs[0]), PMX4UE_OUTPUT=str(out))
        argv = ue(ROOT / "tools/ue_rig.py")
    elif stage == "retarget-pose":
        require(p.get("retarget_pose_profile"), "Set pmx4ue.retarget_pose_profile to a reviewed pose profile")
        inputs = [Path(p["retarget_pose_profile"])]
        env.update(PMX4UE_POSE_PROFILE=str(inputs[0]), PMX4UE_OUTPUT=str(out))
        argv = ue(ROOT / "tools/ue_retarget_pose.py")
    elif stage == "physics-inventory":
        inputs = [Path(c["source"]["pmx"])]
        argv = blender(LEGACY / "blender_pmx_physics_inventory.py", "--config", config, "--output", out)
    elif stage == "physics-plan":
        inputs = [a / "physics_inventory.json", profile, a / "physics_inspect.json"]
        argv = py("pmx_physics_plan.py", "--inventory", inputs[0], "--profile", profile,
                  "--mesh-inspection", inputs[2], "--output", out)
    elif stage.startswith("physics-") or stage == "performance":
        inputs = [profile] if stage == "physics-inspect" else [a / "physics_plan.json"]
        env.update(PMX_PHYSICS_STAGE=stage.removeprefix("physics-"), PMX_PHYSICS_OUTPUT=str(out),
                   PMX_PHYSICS_PROFILE=str(profile), PMX_PHYSICS_PLAN=str(a / "physics_plan.json"))
        if stage == "performance":
            inputs += [a / "physics_test.json"]
            outputs += [a / "performance_review.json"]
            env.update(PMX_PHYSICS_TEST_REPORT=str(inputs[1]), PMX_PIE_CLOSE="1")
        argv = ue(ROOT / "tools/ue_physics_performance.py" if stage == "performance" else LEGACY / "ue_pmx_physics_workflow.py", pie=stage == "performance")
    return dict(stage=stage, argv=argv, env=env, internal=internal,
                inputs=list(map(str, inputs)), outputs=list(map(str, outputs)))


def run(c, project, a, stage, execute=False, timeout=1800):
    # Resolve the selected derived FBX, never mutate the source mesh to repair physics.
    if c["pmx4ue"]["skeleton_policy"] == "upper-only":
        c["paths"]["fbx"] = str(a / "upper_only.fbx")
    spec = recipe(c, project, a, stage)
    if not execute:
        return spec
    require(all(Path(f).is_file() for f in spec["inputs"]), "Missing stage inputs: " + str(spec["inputs"]))
    require(not any(Path(f).exists() for f in spec["outputs"]), "Outputs exist; inspect them or choose a new variant, no silent overwrite")
    if stage in {"ue-build", "ik", "retarget-pose", "physics-build", "physics-test", "performance"}:
        from tools.skeleton_gate import verify, verify_import
        spec["inputs"] += verify(c, a)
        if stage != "ue-build":
            spec["inputs"] += verify_import(c, a, stage)
    if stage == "scene-effects-build":
        require(read(a / "material_compile.json").get("status") == "compiled_visual_pending",
                "Compile baseline materials before scene-effect candidates")
    if stage == "material-preview":
        from tools.material_preview_contract import validate, verify_environment_review
        preview = validate(read(spec["inputs"][0]), c["paths"]["ue_root"], c["pmx4ue"].get("material_source_mesh"))
        spec["inputs"] += verify_environment_review(preview)
        require(read(spec["inputs"][1]).get("status") == "compiled_visual_pending", "Complete material-compile before preview")
    with project_lock(project):
        a.mkdir(parents=True, exist_ok=True)
        record = dict(spec, started=time.time(), status="running", config=c,
                      input_sha256={f: sha(f) for f in spec["inputs"]},
                      code_sha256={str(f.relative_to(ROOT)): sha(f) for f in [Path(__file__), *ROOT.glob("tools/**/*.py")]})
        if stage == "material-build":
            paths = [c["pmx4ue"]["material_source_mesh"], *c["pmx4ue"].get("material_texture_assets", {}).values()]
            record["asset_sha256"] = {}
            for asset in paths:
                require(isinstance(asset, str) and re.fullmatch(r"/Game/[A-Za-z0-9_/]+(?:\.[A-Za-z0-9_]+)?", asset), "Retained input must be a saved /Game asset")
                filename = project.parent / "Content" / (asset.split('.')[0][6:] + ".uasset")
                require(filename.is_file(), "Retained input file missing: " + str(filename))
                for candidate in (filename, filename.with_suffix('.uexp'), filename.with_suffix('.ubulk')):
                    if candidate.is_file():
                        record["asset_sha256"][str(candidate)] = sha(candidate)
        record_path = a / "runs" / f"{time.time_ns()}_{stage}.json"
        log = record_path.with_suffix(".log")
        write(record_path, record)
        write(a / "resolved_config.json", c)
        try:
            if spec["internal"] == "audit":
                write(spec["outputs"][0], build_source_audit(c, project.parent))
            elif spec["internal"] == "draft":
                write(spec["outputs"][0], build_material_map_draft(c, read(spec["inputs"][0])))
            elif spec["internal"] == "delivery":
                from tools.delivery_contract import review_delivery
                verdict = review_delivery(read(spec["inputs"][0]), project)
                write(spec["outputs"][0], verdict)
                record["evidence_sha256"] = verdict["evidence_sha256"]
                require(verdict["status"] == "evidence_complete_needs_human_judgment", "Delivery incomplete; see delivery_check.json")
            else:
                with log.open("w", encoding="utf-8") as stream:
                    result = subprocess.run(spec["argv"], env={**os.environ, **spec["env"]},
                                            cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout,
                                            creationflags=(0 if stage == "material-preview" else
                                                           getattr(subprocess, "CREATE_NO_WINDOW", 0)))
                record["process_exit_code"] = result.returncode
                require(result.returncode == 0, f"Process exited {result.returncode}; see {log}")
                text = log.read_text(encoding="utf-8", errors="replace")
                record["import_risks"] = sorted({token for token in ("invalid bind poses", "zero length normal")
                                                  if token in text.lower()})
            require(Path(spec["outputs"][0]).is_file() if stage == "performance" else all(Path(f).is_file() for f in spec["outputs"]), "Process ended without expected output")
            if stage == "material-build":
                require(all(Path(f).is_file() and sha(f) == value for f, value in record["asset_sha256"].items()),
                        "Retained mesh/texture changed during material-only build")
            if stage == "material-preview":
                from tools.material_preview_contract import verify_report
                preview = read(spec["outputs"][0])
                require(preview.get("profile_sha256") == record["input_sha256"][spec["inputs"][0]], "Preview profile changed during execution")
                verify_report(preview)
                record["capture_sha256"] = {r["image"]["path"]: r["image"]["sha256"] for r in preview["captures"]}
                record["asset_sha256"] = preview["input_assets"]["game_package_sha256"]
            if stage == "performance":
                from tools.review_physics_benchmark import review
                raw = read(spec["outputs"][0])
                policy = read(a / "physics_plan.json")["performance_test"]
                verdict = review(raw, "Candidate", "NoPhysics", record["process_exit_code"],
                                 repeats=policy["repeats"], target_size=(policy.get("viewport_width", 1920), policy.get("viewport_height", 1080)),
                                 minimum_average_fps=policy["minimum_average_fps"], maximum_p99_ms=policy["maximum_p99_ms"])
                write(a / "performance_review.json", verdict)
                record["performance_review"] = verdict
                require(verdict["status"] != "invalid_measurement", "Invalid performance measurement; inspect performance_review.json")
            record.update(status="executed_needs_review", output_sha256={f: sha(f) for f in spec["outputs"]})
            if record.get("import_risks"):
                record.update(status="executed_with_import_risks", production_accepted=False,
                              next_action="Inspect importer log and binding evidence; successful import is not skeleton acceptance")
        except Exception as error:
            record.update(status="failed", error=str(error))
            raise
        finally:
            record["ended"] = time.time()
            write(record_path, record)
    return {"record": str(record_path), "status": record["status"], "outputs": spec["outputs"]}


def status(a):
    rows = []
    for path in sorted((a / "runs").glob("*.json")):
        row = read(path)
        stale = [f for f, value in {**row.get("input_sha256", {}), **row.get("output_sha256", {}),
                                  **row.get("capture_sha256", {}), **row.get("asset_sha256", {}),
                                  **row.get("evidence_sha256", {})}.items()
                 if not Path(f).is_file() or sha(f) != value]
        rows.append(dict(stage=row["stage"], status=row["status"], changed_files=stale, record=str(path)))
    return {"runs": rows, "note": "Execution is not visual acceptance. Changed inputs require agent review before reuse."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    for name in ("id", "pmx", "project", "output"):
        init.add_argument("--" + name, required=True)
    init.add_argument("--variant", default="v1")
    init.add_argument("--source-root")
    init.add_argument("--scale", type=float, required=True, help="Meters per PMX unit, determined by source review")
    init.add_argument("--blender")
    init.add_argument("--engine")
    for name in ("doctor", "status", "run", "install-plugin"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--config", required=True)
        if name == "run":
            cmd.add_argument("--stage", required=True, choices=STAGES)
            cmd.add_argument("--execute", action="store_true", help="Without this flag print plan only")
            cmd.add_argument("--timeout", type=int, default=1800)
        if name == "install-plugin":
            cmd.add_argument("--apply", action="store_true")
            cmd.add_argument("--source", help="Optional BuildPlugin packaged output with binaries")
    args = parser.parse_args()
    if args.command == "init":
        result = initialize(args)
    else:
        c, project, a = load(args.config)
        if args.command == "doctor":
            result = doctor(c, project)
        elif args.command == "status":
            result = status(a)
        elif args.command == "install-plugin":
            result = install_plugin(project, args.apply, args.source)
        else:
            result = run(c, project, a, args.stage, args.execute, args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
