# 骨骼、单位、IK

## 基线与单位

`audit` 读取 PMX/纹理证据；确认单位后设置 `pmx4ue.source_scale_reviewed=true`。`export` 从源 PMX 构建 Blender 场景，先保存米制 `.blend`，随后只在内存中把 mesh、形态键、rest bones 转换为厘米，再输出 FBX；FBX 不能靠根骨 Scale=100 补偿尺寸。`blender_fbx_units.py` 检查 FBX 单位和根缩放。UE 导入比例为 1，不再乘 100。

`skeleton-audit` 读取已保存的源 `.blend`，输出权重、层级、骨骼引用。静态外观正确并不证明 bind pose 或动画正确。不要仅凭截图中骨骼显示长度或 component scale 判断 local scale；比较同一坐标空间。

**已知未解决项：** 本仓库独立导入测试仍出现 Interchange `invalid bind poses` / time-zero rebind 警告。当前厘米路径是隔离实验基线，不是已经证明可无警告替换生产资产的导出器。遇到该警告将骨骼验收标为待处理，不能只设 use_t0_as_ref_pose 掩盖。使用 `blender --background --python tools/legacy/blender_audit_fbx_bind_pose.py -- <文件.fbx>` 对比 BindPose / TransformLink；该静态对比也不能代替 UE 动态蒙皮验证。记录具体引擎导入日志、骨名与矩阵，再决定是否修正 FBX 导出适配。

## 默认保留、按需优化上半身

默认 `pmx4ue.skeleton_policy="preserve"`：导出基线直接使用，不修改腿骨。若用户需要上半身清理：

1. 根据实际 audit 填 `skeleton.roles` 的 `left`、`right` 和 `torso`。键的含义见 `tools/legacy/skeleton_review.py:resolved_roles`，示例语义：`upper_arm`、`elbow`、`wrist`、`upper_twist`、`forearm_twist`、`shoulder`。名称必须来自这个模型，非英文骨名可直接保留。
2. 设置 `skeleton_policy="upper-only"`、`skeleton_reviewed=true`。是否简化肩链由 `skeleton.simplify_shoulders` 显式决定。
3. `skeleton-plan` 只产生重挂父级/已证实无权重叶节点删除计划。`skeleton-apply` 验证源文件身份、保留顶点组，比较静态位置与上半身采样姿势，然后输出独立 `upper_only.fbx`。
4. 引用/约束阻止修改时分析其语义；可新增仅用于导出的适配步骤，不能简单清空检查结果。加测试证明替代方案。参考姿势阈值通过仍不代表重定向通过。

运行器不会调用腿骨清理。旧算法及其测试保留作为归档，不是默认建议；不需要额外增加“腿骨没变”的重复操作。

## IK 与动画

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

Rig 配置完成并不等于动画导出完成。当前工具不自动导出重定向动画，agent 在编辑器或新增受测脚本中调整姿势、检查 pelvis motion/root motion，导出**新的**目标动画。不得更改原动画的 root lock 来隐蔽结果差异。

用真实权重判断普通 leg 与 D leg 哪条驱动 mesh，而不是名字判定。MMD 上半身和下半身的共同父链必须继承 pelvis 位移；上下身分离时对比已知正常版本的层级、局部/组件变换、重定向输出，不能只反复改 Root 开关。根运动根与 pelvis 的语义不同，不强迫给没有对应语义的骨骼建立 Root 链。

最低动态验收：idle、walk、转身/急停，必要时大幅动作；查看腰部连接、腿部、脚底与根位移。动画在目标 skeleton 正常后才进入物理的移动验收。
