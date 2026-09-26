"""UE commandlet stages: inspect (read-only), build (new assets), test (fresh process).

Required env: PMX_PHYSICS_STAGE, PMX_PHYSICS_OUTPUT.
inspect also needs PMX_PHYSICS_PROFILE; build/test need PMX_PHYSICS_PLAN.
No mesh, source animation or level is saved. Existing outputs are not replaced.
"""
import hashlib
import json
import os
import time
from pathlib import Path

import unreal

api = unreal.PMX4UEPmxSkirtTools


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def checked(encoded):
    result = json.loads(encoded)
    if result.get("status") == "error":
        raise RuntimeError(result)
    return result


def main():
    stage = os.environ["PMX_PHYSICS_STAGE"]
    output = Path(os.environ["PMX_PHYSICS_OUTPUT"])
    if output.exists():
        raise RuntimeError("Report already exists; choose a new output")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"stage": stage, "status": "running"}

    def persist():
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    try:
        if stage == "inspect":
            profile = json.loads(Path(os.environ["PMX_PHYSICS_PROFILE"]).read_text(encoding="utf-8"))
            report = checked(api.inspect_physics_mesh(profile["mesh"]))
            persist()
            return
        plan_path = Path(os.environ["PMX_PHYSICS_PLAN"])
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("schema") != "mmd2ue.pmx-physics-plan.v1" or plan.get("status") != "ready":
            raise RuntimeError("Plan is not ready")
        fingerprint = digest(plan)
        report.update(plan=str(plan_path), plan_sha256=fingerprint, assets={}, tests={})
        parts = plan["partitions"]
        paths = [p["asset"] for p in parts]
        all_paths = paths + [plan["rest_blueprint"], plan["walk_blueprint"]]
        controls = plan.get("performance_controls", {})
        all_paths += list(controls.values())
        deferred = plan.get("simulation", {}).get("timing", "synchronous") == "deferred"
        report["simulation"] = plan.get("simulation", {"timing": "synchronous"})
        if len(all_paths) != len(set(all_paths)):
            raise RuntimeError("Duplicate destination asset")
        animation = unreal.load_asset(plan["animation"])
        mesh = unreal.load_asset(plan["mesh"])
        if not animation or not mesh or animation.get_editor_property("skeleton") != mesh.get_editor_property("skeleton"):
            raise RuntimeError("Animation/mesh skeleton mismatch or missing asset")
        inspection = checked(api.inspect_physics_mesh(plan["mesh"]))
        if digest(inspection) != plan["mesh_inspection_sha256"]:
            raise RuntimeError("Target mesh inspection changed; regenerate plan")
        if stage == "build":
            if any(unreal.EditorAssetLibrary.does_asset_exist(p) for p in all_paths):
                raise RuntimeError("Destination exists; use a new profile variant; no overwrite/resume of partially built assets")
            if hashlib.sha256(Path(parts[0]["source_pmx"]).read_bytes()).hexdigest() != plan["source_sha256"]:
                raise RuntimeError("PMX source changed")
            for i, part in enumerate(parts):
                path = output.parent / (output.stem + f"_partition_{i}.json")
                if path.exists():
                    raise RuntimeError("Partition manifest output exists")
                path.write_text(json.dumps(part, indent=2, ensure_ascii=False), encoding="utf-8")
                report["assets"][part["asset"]] = checked(api.build_experiment(str(path)))
                persist()
            for path, clip in ((plan["rest_blueprint"], ""), (plan["walk_blueprint"], plan["animation"])):
                report["assets"][path] = checked(api.build_physics_blueprint(plan["mesh"], paths, clip, path, deferred))
                persist()
            for kind, path in controls.items():
                report["assets"][path] = checked(api.build_physics_blueprint(
                    plan["mesh"], [] if kind == "no_physics" else paths, plan["animation"], path, False))
            for path in all_paths:
                asset = unreal.load_asset(path)
                unreal.EditorAssetLibrary.set_metadata_tag(asset, "MMD2UE.PhysicsPlanSHA256", fingerprint)
                if not unreal.EditorAssetLibrary.save_loaded_asset(asset):
                    raise RuntimeError("Could not save provenance: " + path)
            report["status"] = "built_pending_fresh_process_test"
        elif stage == "test":
            for path in all_paths:
                asset = unreal.load_asset(path)
                if not asset or unreal.EditorAssetLibrary.get_metadata_tag(asset, "MMD2UE.PhysicsPlanSHA256") != fingerprint:
                    raise RuntimeError("Missing asset or plan provenance mismatch: " + path)
            expected_names = {b["target_bone"] for p in parts for b in p["bodies"] if not b["kinematic"]}
            expected_filters = sum(len(p["bodies"]) for p in parts)
            expected_actors = sum(len({b["target_bone"] for b in p["bodies"]}) for p in parts)
            for tag, bp, fps, move in (("rest_60", plan["rest_blueprint"], 60., False),
                                       ("walk_60", plan["walk_blueprint"], 60., False),
                                       ("walk_move_turn_60", plan["walk_blueprint"], 60., True),
                                       ("walk_move_turn_30", plan["walk_blueprint"], 30., True)):
                started = time.perf_counter()
                result = checked(api.test_experiment(plan["mesh"], bp, 12., fps, move, False, plan["measurement_anchor"]))
                result["wall_seconds_including_setup"] = time.perf_counter() - started
                report["tests"][tag] = result
                persist()
                if result["status"] != "measured" or result["evaluated_frames"] != round(12*fps):
                    raise RuntimeError("Simulation did not complete/advance: " + tag)
                if (result["shape_filter_errors"] or result["applied_shape_filters"] != expected_filters
                        or result["native_rigidbody_actors"] != expected_actors
                        or set(result["simulated_bone_names"]) != expected_names):
                    raise RuntimeError("Runtime bodies/filter/ownership mismatch: " + tag)
                settings = result["runtime_solver_settings"]
                expected = {p["asset"]: p for p in parts}
                if len(settings) != len(parts) or {s["asset"].split(".")[0] for s in settings} != set(expected):
                    raise RuntimeError("Runtime solver partitions mismatch")
                for setting in settings:
                    part = expected[setting["asset"].split(".")[0]]
                    solver = part.get("solver", dict(position_iterations=16, fixed_time_step=1/120, use_linear_joint_solver=False))
                    if (setting["timing"] != ("deferred" if deferred else "synchronous")
                            or setting["position_iterations"] != solver["position_iterations"]
                            or abs(setting["fixed_time_step"]-solver["fixed_time_step"]) > 1e-7
                            or setting["use_linear_joint_solver"] != solver["use_linear_joint_solver"]):
                        raise RuntimeError("Runtime solver settings differ from plan")
            report["status"] = "numerically_measured_visual_and_performance_pending"
            report["pending"] = ["Startup transient", "Garment/body penetration in actual animation",
                                 "Normal-material shading", "Real-time performance and game integration"]
        else:
            raise RuntimeError("Unknown stage: " + stage)
        persist()
    except Exception as error:
        report.update(status="blocked", error=str(error))
        persist()
        raise
    unreal.log("PMX_PHYSICS_WORKFLOW " + report["status"] + " " + str(output))


main()
