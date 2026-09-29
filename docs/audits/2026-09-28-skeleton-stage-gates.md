# 上肢处理与物理阶段入口审核 — 2026-09-28

## 后续修复状态

以下原审计保留为问题来源，不再代表所有问题仍未修复。现已修复直接主链漏判 P/C、规划提前退出、残留骨逐项保留决策缺失、apply/UE 层级后置条件缺失、导入风险记录放行，以及支持的 IK/物理脚本绕过外层入口的问题。新增 shoulder cleanup 回归覆盖直接/半直链、残留 P/C、权重/引用/挂件保护及导入门槛。详见骨骼参考的迁移规则和 VERIFICATION.md 最新记录。

边界仍然存在：骨骼 morph/PMX 追加变换等完整语义审计、所有动作的视觉验收、任意自写脚本的执行约束不在这些自动结构检查的证明范围内。不能将结构回执升级成全动作或生产级物理验收。

范围：当前工作流源码、现有测试，以及 DeepSeekTest 的配置/审计输出（只读）。本次不修改任何角色骨架、不启动物理实验、不提交；以下是待修复发现，不是已完成修复。

## 结论

目前流程可以证明“执行了所选操作”，不能充分证明“手臂和肩膀的约定目标已全部实现并在 UE 中验收”。允许部分完成流向物理阶段的路径真实存在；不是简单增加一次 reviewed 标记就能解决。

## 已复现及源码证据

### P1：肩链变直会漏掉残留 P/C

`tools/legacy/skeleton_review.py:analyze_audit` 用 torso→shoulder→arm 主链判断 direct_single_shoulder_chain；即使 helper_bones 中仍有 P/C 也可判定 direct。`tools/skeleton_gate.py:verify` 只对状态含 intermediate 的 preserve 请求保留证据。

使用现有测试 fixture，在两侧直接肩链旁增加无权重 P/C，当前 verify 返回成功（三个依赖文件），无需任何 helper 的保留依据。这个复现为合成数据，不代表目标模型所有 P/C 都已证明可删除。

### P1：simplify_shoulders=true 不保证产生肩膀操作

`tools/legacy/skeleton_plan.py:build_plan` 遇到直接肩链提前 continue，未检查残留 helpers。复现：同一 fixture 加上手臂 twist 中间骨，启用 simplify_shoulders，返回 status=ready，但操作只有左右 elbow 的 reparent，没有任何肩膀操作。当前入口只对照布尔选项与总计划，没有逐部位最终结果检查。

### P1：保留证据没有逐骨结构化语义

当前 preservation_evidence 仅要求文件存在且 SHA 一致，不校验左右每个 helper 的权重、约束、子物体/附加结构、用途或审批结论。肩膀被记为 preserve 后，即使肩部优化目标未完成，也能以 arms=optimize 形成有效 upper-only 计划。文件真实存在不等于内容足以支持保留。

### P1：导出成功与 UE 骨骼验收没有分离

apply 有静态顶点、rest matrix 和肩/肘/腕采样姿势比较，是有效的导出保护，但报告明确 animation_validation=pending。verify 主要比对 operations、导出文件与运行哈希，没有导出后全上肢逐骨结果审计，也没有 UE 导入后的最终层级与目标结果比对。

verify_import 接受 executed_with_import_risks。运行器本身把此状态标记 production_accepted=false，并要求先处理绑定风险；下游入口却仍放行。物理脚本检查 mesh inspection 与计划是否一致，只能证明“同一网格”，不能证明“骨骼已完成”。

### P1：入口防护仅在外层运行器

pmx4ue.run 在部分阶段调用骨骼 gate；`tools/ue_rig.py` 与 `tools/legacy/ue_pmx_physics_workflow.py` 内部未检查同一骨骼验收凭据。agent 直接通过 UE Python 调这些支持脚本可以绕开外层检查。完全自写脚本无法技术上禁止，但受支持入口应一致，并拒绝把缺证据的产物纳入正式交付。

### P2：审计覆盖不足以宣称 P/C 已证实“无作用”

blender_skeleton_audit 收集权重、层级、部分 Blender constraints/drivers/actions 和骨骼挂载对象；不等同于完整 PMX 语义依赖检查，未显式统一解析追加变换、骨骼 morph、刚体/关节等引用。零顶点权重不能单独批准删除。应在导出变体上处理必要转换，不删除原 PMX，也不为安全而不加区分地保留所有 helper。

### P2：验证用例偏重流程文件，没有覆盖最终清理目标

现有 readiness 用例检查 review 缺失、手臂 intermediate、apply 来源和错误 target mesh；缺失“主链直接但 P/C 尚在”“只改手臂却声明肩膀完成”“保留证据未覆盖某一侧”“绑定风险未关闭仍构建物理”“直接入口绕过”等回归。

## 外部副本版本边界

只读检查到 DeepSeekTest 副本的 pmx4ue.run 没有当前 skeleton_gate 调用。其 Nikketa/v1 resolved_config 仍为 preserve、skeleton_reviewed=false；该目录有 skeleton_audit 和 physics_inventory，未发现 skeleton_apply / physics_build 报告。不能据此断言它已经执行了用户本次提到的物理编辑，也不能把它当作最新工作流已生效的证据。

该源审计中的双侧 ShoulderP/C 权重均为零，P 下还存在 _dummy_ShoulderC，右侧实际 Shoulder 有 Badge 挂件。需要逐项处理这些结构；本审计没有证明“名称带 P/C 就能直接删”。

## 修复目标（尚未实施）

1. 每侧明确 upper-arm/elbow/wrist 与 shoulder/P/C/helper 的实际语义；输出每个 helper 的 remove/retain_with_evidence/blocked 决定。已确认冗余者删除，必要者明确保留，不把缺能力转换为已完成。
2. 计划必须覆盖所有选定部位；定义最终父链、应删除骨、保留骨和挂件归属的后置条件。apply 后重新审计，再对 UE 实际导入结果读回验证。不是反复检查未动腿骨。
3. 将 source_audited、plan_reviewed、applied、ue_skeleton_accepted、motion_accepted 分开；文件 hash 支持可追溯，不能代替最后两项。
4. IK 生成/姿态调试需要 UE 骨骼结构与绑定验收；物理构建也必须先满足它，未解决绑定风险不得放行。只读 PMX inventory 和草稿可以提前，但不得标为已开始/完成物理资产编辑。
5. 静态物理测试不必等待不存在的动画；持续移动物理测试则需要目标动画已验证。避免循环依赖：骨骼结构先验收，再建 IK/重定向，再动作验收，再移动物理。
6. 同一验收检查接到运行器和受支持 UE 写入脚本，绑定当前 mesh/骨架/导入来源指纹；旧批准不适用于重新导入资产。角色自定义适配仍允许，但必须提供同一结果合同。
7. 先补上述失败用例，再改逻辑，并在指定实验工程的新资产版本验证肩抬举、手臂扭转和挂件/布料挂接。不要用单测全绿替代 UE 结果。
