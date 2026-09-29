"""Capability-based native bridge selection; never installs a plugin."""
import json

CAPABILITIES = {
    "physics": ("PmxSkirtTools", ("inspect_physics_mesh", "build_experiment", "build_physics_blueprint", "test_experiment")),
    "workflow": ("WorkflowTools", ("configure_physics_blueprint", "test_motion", "begin_preview_window", "set_preview_resolution")),
    "retarget": ("RetargetTools", ("inspect_retarget_pose",)),
    "visual": ("AgentMCPTools", ("frame_preview_subject", "capture_visible_editor_viewport")),
    "materials": ("AgentMCPTools", ("inspect_material_compile",)),
}


def resolve(kind, module=None):
    if module is None:
        import unreal as module
    suffix, methods = CAPABILITIES[kind]
    found = [(prefix, getattr(module, prefix+suffix, None)) for prefix in ("MMD2UE", "PMX4UE")]
    found = [(p, cls) for p, cls in found if cls is not None]
    if len(found) > 1:
        raise RuntimeError("Duplicate bridge providers loaded; do not install PMX4UE into MMD2UE")
    if not found or any(not callable(getattr(found[0][1], m, None)) for m in methods):
        raise RuntimeError("Missing/outdated native capability: " + kind + "; compile the existing host module or standalone plugin, never install a duplicate")
    return found[0][1]


def inventory(module=None):
    if module is None:
        import unreal as module
    result = {}
    for key in CAPABILITIES:
        try:
            cls = resolve(key, module)
            result[key] = dict(available=True, provider=cls.__name__)
        except RuntimeError as error:
            result[key] = dict(available=False, reason=str(error))
    return result


def checked(encoded):
    data = json.loads(encoded)
    if "error" in data or data.get("status") in ("error", "failed", "blocked"):
        raise RuntimeError(data)
    return data
