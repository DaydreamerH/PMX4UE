---
name: pmx-to-ue
description: Use the PMX4UE workbench to convert PMX characters into Unreal Engine meshes, materials, IK and PMX-derived physics, including model-specific script adaptation and validation.
---

# PMX → UE

This skill is packaged with the PMX4UE repository. Resolve the repository two levels above this folder. Keep the entire repository when moving it; copying SKILL.md alone does not include its tools.

Read repository `AGENTS.md`. Work as a technical agent, not a blind script runner: inspect the PMX and target UE hierarchy, decide which existing adapters fit, and implement narrowly scoped adaptations when needed. Reviewer flags represent evidence-based agent decisions; they are not instructions to ask the user every technical question.

Read the relevant reference completely before that phase:

- [environment.md](references/environment.md): new project, dependencies, paths, operation records.
- [skeleton.md](references/skeleton.md): scale, bind pose, upper-body optimization, IK and animation.
- [materials.md](references/materials.md): optional target-image analysis, texture/slot reasoning, material implementation and appearance checks.
- [physics.md](references/physics.md): PMX inventory, partition semantics, native RigidBody, performance.
- [adaptation.md](references/adaptation.md): unsupported models, experiments, reusable fixes and handoff.

Keep source assets intact. Generate new variants, not silent overwrites. Preserve legs by default; do not alter a working mesh to conceal a physics bug. PMX group numbers are not themselves collision isolation: evaluate reciprocal masks. Do not add garment avoidance that the source does not request.

Default skeleton target is UE FK retargeting, not PMX/VMD control-animation compatibility. Read `docs/ue-fk-skeleton.md` at repository root: keep weighted twist bones as branches and move P/C out of the actual main path. Weighted/helper dependencies are not a reason to preserve a dirty main hierarchy; choosing IK endpoints does not alter that hierarchy. New work orders use `clean_ue_fk` with `branch_helpers`.

Target-image analysis is optional. When images are supplied for this purpose, inspect relevant material features and compare the rendered result. Without them, proceed from the PMX, textures and written requirements; do not block work waiting for images. Distinguish target images from diagnostic screenshots.

Ground material algorithms in the actual mesh and texture data. Separate observed facts from implementation hypotheses; verify the geometry layers, UVs and channel meaning required by a candidate before changing transparency or assuming transmission. See the asset-first checks in `docs/material-families.md` at the repository root.

Use `pmx4ue.py` for common operations, or explicit tools for justified exceptions. The runner is an auditable convenience, not a restriction on adapting code. Its dry-run output lists argv and expected files; run with `--execute` only when prerequisites are established. Inspect logs and output evidence after each stage.

Complete only what has actually been tested. Lack of animation blocks movement acceptance, not material work. Report unsupported semantics and performance/visual limitations without disguising them as successful conversion. Save a handoff with enough raw paths and commands for another agent to continue without this conversation.
