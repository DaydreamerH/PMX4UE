# 骨骼、单位、IK

## 基线与单位

`audit` 读取 PMX/纹理证据；确认单位后设置 `pmx4ue.source_scale_reviewed=true`。`export` 从源 PMX 构建 Blender 场景，先保存米制 `.blend`，随后只在内存中把 mesh、形态键、rest bones 转换为厘米，再输出 FBX；FBX 不能靠根骨 Scale=100 补偿尺寸。`blender_fbx_units.py` 检查 FBX 单位和根缩放。UE 导入比例为 1，不再乘 100。

`skeleton-audit` 读取已保存的源 `.blend`，输出权重、层级、骨骼引用。静态外观正确并不证明 bind pose 或动画正确。不要仅凭截图中骨骼显示长度或 component scale 判断 local scale；比较同一坐标空间。

**绑定精度修正：** 原路径的 float32 累积矩阵漂移曾导致 Interchange `invalid bind poses`。厘米导出现在经 `tools/blender_fbx_bind.py` 修正近单位绑定基底和相对矩阵：仅允许 ≤100ppm 的尺度漂移，保持平移、模型局部变换、层级、几何/权重不变，并重读 FBX 校验全部字段。非单位/反射/真实绑定不一致会拒绝处理。普通导出保留 `.raw.fbx`，manifest 记录修正量。托洛洛完整 SDK 绑定检查与 UE 新目录导入已通过，不再有该绑定告警；不能据此免除新角色的蒙皮和动作验收。仍有 zero length normal 消息，需独立处理几何/法线。

新模型仍出现绑定警告时将骨骼验收标为待处理，不能设 use_t0_as_ref_pose 掩盖。`blender_audit_fbx_bind_pose.py` 只是序列化矩阵诊断（多 mesh 对比有限），不能代替 SDK/UE 验证。精度修正也不能处理错误父级、错单位或真正的非单位骨缩放。

## 先审阅上肢，再决定保留或优化

**UE 重定向优先：** 先执行 [UE FK 骨架方案](../../../docs/ue-fk-skeleton.md)。新工作单以 `clean_ue_fk + branch_helpers` 为目标；不要求兼容原 PMX 控制动画。手臂扭转骨有权重、P/C 有补偿，都不构成原层级必须保留的理由。先实际整理主链，删除辅助骨只是可选的进一步精简。下述删除模式和保留证据仍适用于旧工作单及已干净的旁支。

初始 `pmx4ue.skeleton_policy="preserve"` 只是防止未经审阅就改骨，不代表可以直接进入 IK/物理。每个角色都要运行 `skeleton-audit → skeleton-review`，审阅双侧手臂和肩链；命名映射由 agent 根据真实数据完成。链条已经直接、或中间骨具有必要变形/约束语义时可以保留，不以删除骨骼数量考核优化。

把 `templates/skeleton_decision.example.json` 复制到产物目录的 `skeleton_decision.json`（或通过 `pmx4ue.skeleton_decision` 指定绝对路径），填写当前 audit 和源 blend 的 SHA256、与工作单一致的 `roles`，以及 `arms`、`shoulders` 各自的 `action=preserve/optimize` 和理由。保留包含中间骨的链时附 `preservation_evidence: [{"path":"绝对路径", "sha256":"文件哈希"}]`，内容必须解释权重/约束/变形试验，不是简单写“默认保留”。未知骨名/路径先适配，不能勾选 reviewed 绕过。

选择优化时：

1. 根据实际 audit 填 `skeleton.roles` 的 `left`、`right` 和 `torso`。键的含义见 `tools/legacy/skeleton_review.py:resolved_roles`，示例语义：`upper_arm`、`elbow`、`wrist`、`upper_twist`、`forearm_twist`、`shoulder`。名称必须来自这个模型，非英文骨名可直接保留。
2. 设置 `skeleton_policy="upper-only"`、`skeleton_reviewed=true`。是否简化肩链由 `skeleton.simplify_shoulders` 显式决定。
3. `skeleton-plan` 只产生重挂父级/已证实无权重叶节点删除计划。`skeleton-apply` 验证源文件身份、保留顶点组，比较静态位置与上半身采样姿势，然后输出独立 `upper_only.fbx`。
4. 引用/约束阻止修改时分析其语义；可新增仅用于导出的适配步骤，不能简单清空检查结果。加测试证明替代方案。参考姿势阈值通过仍不代表重定向通过。

### 肩膀完整清理与旧记录迁移（2026-09-28）

主链已经是 torso → shoulder → upper_arm，并不代表清理完成：仍存在映射后的 P/C 时，review 标为 `residual_shoulder_helpers`。选择 optimize 后，规划器也会检查旁支残留、部分改直的链；无权重且无被引用依赖的 P/C 才能删除。额外待清理骨在每侧 `shoulder_helpers` 列出，不按名称通配删除。删除骨的保留子骨必须逐一填写 `rehome_before_delete`；带权重的肩、扭转和辅助变形骨不删除。

若决定保留残留骨，`shoulders.helper_decisions` 必须覆盖 review 返回的每个 helper，逐骨填写 `action="retain"`、`reason`、`evidence_path`，后者指向 `preservation_evidence` 中的实际证据文件。证据内容仍由 agent 审阅，文件哈希不是语义正确性的证明。

新 plan 含 `postconditions.absent/parents`；apply 报告含 `final_bone_parents` 和后置条件回执。UE 导入后再次从真实 mesh 读取父级，写入 `ue_build_report.skeleton_structure`。支持的 IK/物理写入口同时检查这些证据和实际目标 mesh；带未解决导入风险的记录不放行。缺少新字段的旧 plan/apply/import 报告不可补一个 passed 标记迁移，应重新执行对应阶段并保存新版本产物。

此门槛验证结构与导出来源，不等于动作/物理验收。Blender 引用扫描也不等于完整 PMX 追加变换、骨骼 morph、刚体/关节语义证明；存在这些依赖时先分析、适配或明确阻塞，不能以零权重直接认定无用。

`ue-build` 执行前检查这份决策；`ik/retarget-pose/physics-build/physics-test/performance` 同样检查。选择 upper-only 时必须有匹配计划的 apply 报告、导出 FBX 与成功运行记录，之后 IK/物理目标必须使用该 FBX 导入的 mesh，不能又选回原始版本。运行器的 dry-run 只展示命令，不代替上述执行检查。

旧工作单迁移：补上肢 audit/语义/决策，不得把旧 skeleton_reviewed 自动改 true。纯材质迭代的 `material-build` 不要求重导出或重新处理已认可的 mesh；其它复用/自定义入口需要关联原骨骼证据并作显式适配，不通过直接调用 legacy 跳过审阅。

运行器不会调用腿骨清理。旧算法及其测试保留作为归档，不是默认建议；不需要额外增加“腿骨没变”的重复操作。

## IK 与动画

新模型/新配对使用 `docs/agent-retarget-workflow.md` 与 `templates/retarget-agent.md`：先采集，agent 审核真实语义和身体坐标，复用模型档案、单独规划配对，再原生写入与分层验收。不要把某角色的恢复骨名或数值固定成通用默认值。通用入口已在 UEFN→托洛洛完成 UE 原生生成与新进程重载，但不能照搬历史案例的视觉通过状态。

T-Pose 规范化见 `docs/retarget-pose.md`：先确认 Source 与 Target 的实际 mesh/链条，对两侧分别生成命名姿态并验证。MMD2UE 内实验使用真实源动画 Rig 与已经认可的目标 mesh，不以同骨架 smoke test 代替实际对齐；不改绑定姿态。

`tools/draft_profiles.py --config <角色配置>` 在 physics inventory 后可生成 rig/physics 未审核草稿，也可由 agent 自行编写相同结构。rig.json：

```json
{
  "reviewed": true,
  "target": {
    "mesh": "/Game/PMX4UE/MyCharacter/v1/Mesh/SK_MyCharacter",
    "asset": "/Game/PMX4UE/MyCharacter/v1/Rigs/IK_Target",
    "pelvis": "实际的共同躯干驱动骨",
    "chains": {"Spine": ["实际脊柱起点", "实际脊柱终点"]}
  },
  "source": null,
  "retargeter": "/Game/PMX4UE/MyCharacter/v1/Rigs/RTG_SourceToTarget"
}
```

不要直接运行上述中文占位值。agent 从 UE 导入后的层级生成四肢、脊柱、颈头及需要的手指链。`source=null` 只创建目标 IK，空白项目不强行依赖 Manny。若已有源动画骨架，source 使用同结构 mesh/asset/pelvis/chains；新源 Rig 也建在当前变体目录，不改已有源 Rig。`ik` 检查端点存在及父子路径，建立默认 retarget op stack 和同名链映射。

Rig 配置完成并不等于动画导出完成。agent 调整姿势并检查 pelvis motion/root motion 后，使用 `animation-export` 导出新的目标动画，配置见 `templates/animation_export.example.json`。工具检查 Skeleton、RTG 实际配对、独立输出与输入哈希；不得改原动画 root lock 隐蔽差异。真实 UE 5.8.2 导出已验证，视觉动作仍逐例审核。

用真实权重判断普通 leg 与 D leg 哪条驱动 mesh，而不是名字判定。MMD 上半身和下半身的共同父链必须继承 pelvis 位移；上下身分离时对比已知正常版本的层级、局部/组件变换、重定向输出，不能只反复改 Root 开关。根运动根与 pelvis 的语义不同，不强迫给没有对应语义的骨骼建立 Root 链。

最低动态验收：idle、walk、转身/急停，必要时大幅动作；查看腰部连接、腿部、脚底与根位移。动画在目标 skeleton 正常后才进入物理的移动验收。
