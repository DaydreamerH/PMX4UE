"""Configure a repeatable studio preview in the current default editor level.

The stage does not create or load a level asset: it operates on whatever world
is currently open (the editor's built-in Untitled level is the intended target)
and spawns/refreshes the character, key/fill/rim lights, a fixed exposure post
process and a named camera.  This keeps the material reference identical across
characters and avoids accumulating Preview level assets.
"""

from __future__ import annotations

import math
import os

import unreal

from ue_context import safe_set


def _look_at_rotation(origin, target) -> unreal.Rotator:
    dx = target.x - origin.x
    dy = target.y - origin.y
    dz = target.z - origin.z
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.sqrt(dx * dx + dy * dy)))
    return unreal.Rotator(pitch, yaw, 0.0)


def _destroy_previous(cid: str) -> None:
    removable = (
        unreal.SkeletalMeshActor,
        unreal.DirectionalLight,
        unreal.RectLight,
        unreal.PointLight,
        unreal.SpotLight,
        unreal.CameraActor,
        unreal.PostProcessVolume,
    )
    toon_class = getattr(unreal, "MMDToonCharacterActor", None)
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        label = actor.get_actor_label()
        if isinstance(actor, removable) or (toon_class and isinstance(actor, toon_class)) or label.startswith(f"{cid}_"):
            unreal.EditorLevelLibrary.destroy_actor(actor)


def spawn_character(ctx, mesh=None, location=None):
    """Place only the character in the current level, leaving all lighting untouched.

    This is the default-scene workflow: open the editor's default level (which
    already ships a sun/sky), drop the mesh in, frame the camera and capture.
    """
    cid = ctx.names["character_id"]
    label = f"SK_{cid}"
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if actor.get_actor_label() == label:
            return actor
    if mesh is None:
        mesh = unreal.EditorAssetLibrary.load_asset(f"{ctx.names['mesh_root']}/{ctx.names['mesh_asset']}")
    if not isinstance(mesh, unreal.SkeletalMesh):
        raise RuntimeError(f"skeletal mesh not found: {ctx.names['mesh_asset']}")
    spawn_location = location or unreal.Vector(0.0, 0.0, 0.0)
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SkeletalMeshActor, spawn_location, unreal.Rotator(0, 0, 0)
    )
    if actor is None:
        raise RuntimeError("failed to spawn SkeletalMeshActor")
    actor.set_actor_label(label)
    component = actor.get_editor_property("skeletal_mesh_component")
    component.set_skeletal_mesh_asset(mesh)
    component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    return actor


def focus_viewport_on_character(ctx):
    """Frame the current level viewport on the character (script twin of double-click).

    Selects the character actor and runs the editor's own CAMERA ALIGN command,
    which focuses whichever viewport the capture tool will use.
    """
    cid = ctx.names["character_id"]
    actor = None
    for candidate in unreal.EditorLevelLibrary.get_all_level_actors():
        if candidate.get_actor_label() in (f"SK_{cid}", f"{cid}_Preview"):
            actor = candidate
            break
    if actor is None:
        return "actor not found"
    try:
        unreal.EditorLevelLibrary.set_selected_level_actors([actor])
    except Exception:
        pass
    world = unreal.EditorLevelLibrary.get_editor_world()
    if world:
        unreal.SystemLibrary.execute_console_command(world, "CAMERA ALIGN")
    return actor.get_actor_label()


def setup_preview(ctx, mesh, key_light_actor=None):
    """Spawn/refresh the studio rig in the current world.  Returns a report."""
    cid = ctx.names["character_id"]
    preview = ctx.config.get("preview", {}) or {}
    exposure = float(preview.get("exposure_ev100", os.environ.get("MMD2UE_PREVIEW_EXPOSURE_EV100", 3.0)))
    key_intensity = float(preview.get("key_intensity", os.environ.get("MMD2UE_PREVIEW_KEY_INTENSITY", 6.0)))
    fill_intensity = float(preview.get("fill_intensity", os.environ.get("MMD2UE_PREVIEW_FILL_INTENSITY", 300.0)))
    rim_intensity = float(preview.get("rim_intensity", os.environ.get("MMD2UE_PREVIEW_RIM_INTENSITY", 180.0)))

    world = unreal.EditorLevelLibrary.get_editor_world()
    if not world:
        raise RuntimeError("no editor world is loaded; open the default level first")

    _destroy_previous(cid)

    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0)
    )
    if actor:
        actor.set_actor_label(f"{cid}_Preview")
        component = actor.get_editor_property("skeletal_mesh_component")
        component.set_skeletal_mesh_asset(mesh)
        component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        component.set_relative_location(unreal.Vector(0, 0, 0), False, True)

    target = unreal.Vector(0, 0, 105)
    key_location = unreal.Vector(0, 220, 250)
    fill_location = unreal.Vector(160, 90, 150)
    rim_location = unreal.Vector(0, -170, 225)

    key = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.DirectionalLight, key_location, _look_at_rotation(key_location, target)
    )
    fill = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, fill_location, unreal.Rotator(0, 0, 0))
    rim = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.PointLight, rim_location, unreal.Rotator(0, 0, 0))
    for spawned, label in ((key, f"{cid}_Key"), (fill, f"{cid}_Fill"), (rim, f"{cid}_Rim")):
        if spawned:
            spawned.set_actor_label(label)

    for light, intensity, color, cast_shadows, specular_scale in (
        (key, key_intensity, unreal.LinearColor(1.0, 0.88, 0.82, 1.0), True, 1.0),
        (fill, fill_intensity, unreal.LinearColor(0.68, 0.78, 1.0, 1.0), False, 0.0),
        (rim, rim_intensity, unreal.LinearColor(0.68, 0.78, 1.0, 1.0), False, 0.0),
    ):
        if not light:
            continue
        component = light.get_component_by_class(unreal.LightComponent)
        safe_set(component, "intensity", intensity)
        safe_set(component, "light_color", unreal.Color(int(color.r * 255), int(color.g * 255), int(color.b * 255), 255))
        safe_set(component, "cast_shadows", cast_shadows)
        safe_set(component, "specular_scale", specular_scale)
    if key:
        key_component = key.get_component_by_class(unreal.DirectionalLightComponent)
        safe_set(key_component, "source_angle", 2.0)
        # Register as the atmosphere sun (index 0) so the SkyAtmosphere, SkyLight
        # and volumetric clouds are lit by the preview key instead of going dark.
        safe_set(key_component, "atmosphere_sun_light", True)
        safe_set(key_component, "atmosphere_sun_light_index", 0)
        safe_set(key_component, "mobility", unreal.ComponentMobility.MOVABLE)
    if fill:
        safe_set(fill.get_component_by_class(unreal.PointLightComponent), "attenuation_radius", 650.0)

    post_process = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0)
    )
    if post_process:
        post_process.set_actor_label(f"{cid}_ValidationExposure")
        safe_set(post_process, "unbound", True)
        safe_set(post_process, "blend_weight", 1.0)
        settings = post_process.get_editor_property("settings")
        safe_set(settings, "override_auto_exposure_min_brightness", True)
        safe_set(settings, "override_auto_exposure_max_brightness", True)
        safe_set(settings, "auto_exposure_min_brightness", exposure)
        safe_set(settings, "auto_exposure_max_brightness", exposure)
        safe_set(settings, "override_auto_exposure_bias", True)
        safe_set(settings, "auto_exposure_bias", 0.0)
        safe_set(settings, "override_bloom_intensity", True)
        safe_set(settings, "bloom_intensity", 0.15)
        safe_set(post_process, "settings", settings)

    camera_location = unreal.Vector(260, -420, 125)
    camera_target = unreal.Vector(0, 0, 95)
    camera = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.CameraActor, camera_location, _look_at_rotation(camera_location, camera_target)
    )
    if camera:
        safe_set(camera.camera_component, "field_of_view", 38.0)
        safe_set(camera.camera_component, "auto_activate_for_player", 0)
        camera.set_actor_label(f"{cid}_Camera")

    return {
        "level": world.get_path_name(),
        "camera": f"{cid}_Camera",
        "preview_actor": f"{cid}_Preview",
        "exposure_ev100": exposure,
        "key_intensity": key_intensity,
        "fill_intensity": fill_intensity,
        "rim_intensity": rim_intensity,
        "created_level_asset": False,
    }
