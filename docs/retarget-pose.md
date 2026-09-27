# 重定向器 T-Pose 编辑

新模型优先使用 [Agent 主导的通用流程](agent-retarget-workflow.md)，生成可复用模型档案与配对方案；本文保留底层手写配置和历史案例。`pre_edits` 现在支持在自动四肢求解之前修正腰、骨盆或锁骨，`edits` 保持求解后微调语义。

本工具编辑 **UE 原生 IK Retargeter 的 Retarget Pose**。不改 mesh、骨架层级、绑定姿态、权重、原动画，也不做物理模拟。结果仍可在 UE 的姿态编辑模式里继续手调。

本地默认运行在 MMD2UE 原工程，新版本资产也保存在 MMD2UE 内容目录。该工程使用现有 `MMD2UEEditor` 中的 `MMD2UERetargetTools`，不安装带重名物理节点的整套 PMX4UE 插件。只有明确的迁移测试才使用其它工程。

当前 MMD2UE 数值验证版本：`/Game/Characters/TololoSchool1001/Rigs/TPose_v4/RTG_UEFN_To_Tololo_TPose_v4`，两侧分别使用 `TPose_Source_v4` / `TPose_Target_v4`。v4 保留 v3 的上半身，以 Target 自然收拢腿姿匹配 Source 大腿/小腿方向并保持脚掌组件旋转；不强迫不同体型的踝间距相同。视觉/动画验收仍待完成。它基于实际 UEFN→托洛洛 UpperOnlyCm 配对，而非同骨架对照。更换 Rig 后需用 `assign_ik_rig_to_all_ops` 同步操作内部 Rig 引用，并验证链映射；仅设置顶部 Target Rig 不够。

最新链条对照实验：`/Game/Characters/TololoSchool1001/Rigs/TPose_v5/RTG_UEFN_To_Tololo_TPose_v5`。复制独立 Target Rig，把 Spine 从 `Groove → UpperBody2` 缩至 `UpperBody → UpperBody2`，避免把腿部共用祖先 Waist 纳入脊柱旋转链；保留 v4 双侧命名姿态及 Center 骨盆。保存/重载验证通过，但行走偏移是否解决仍待动画验收。根运动旧配置未混改。此项是链语义修正，不是骨骼合并；详见 `characters/TololoSchool1001/spine-v5-decision.md`。

2026-09-27 后续验收：用户查看 v5 后反馈“效果很好”，授权提交整轮尝试。v5 为当前用户认可基线；上方待验收描述是生成时状态，不代表新增了自动动画采样或已验收所有动作。

目前是供 agent/脚本调用的姿态编辑工具，**不是新增一套拖拽式编辑器界面**。

## 支持范围

版本对照：v1 继承躯干后仰；v2 修复上身但遗漏腿部旧补偿；v3 清理 D 腿/膝四处遗留偏移，未匹配 Source 外张站姿；v4 才增加双侧腿段方向匹配。保留旧版本用于排查，不作为当前全身姿态验收结果。

- 按骨骼位置自动将双侧上臂、前臂对齐到身体左右方向；分别支持 Source、Target 或两者。
- 当前姿态作为基底：复制原重定向器和当前命名姿态，创建新的命名姿态再激活。
- 可显式恢复指定骨骼的参考局部旋转，先处理基底，再计算双臂；不把所有骨骼一律清零。
- `leg_alignment` 接收已审核的大腿/小腿组件空间方向，以纯旋转匹配；保持髋宽、骨长及脚掌的组件空间旋转。
- 手动逐骨旋转：局部轴角增量，或者直接指定相对参考姿态的四元数偏移。
- 未指定骨骼保留局部姿态。上臂的子骨骼会正常随父骨转动，不会锁在旧世界坐标。
- 基于 UE 原生解析得到的姿态检查位置/旋转，拒绝旧的非单位骨骼缩放、非法链、退化方向、180° 歧义和已有输出。

初版只自动处理**手臂方向**；v4 增加经审核的腿段方向匹配。仍不自动识别锁骨、手掌朝向/轴向扭转、手指或鞋面接触。最短弧旋转不额外添加轴向扭转，但不等于能判断两个角色的掌心语义。必要时由 agent 根据手指关节、掌面或截图补充旋转。角色必须处于合理中立姿态；T 型不是所有骨骼旋转清零，也不是让不同角色关节位置强行重合。

## 配置与运行

1. MMD2UE 中编译现有 Editor 模块的姿态接口；其它明确指定的工程才安装匹配的 PMX4UE 插件。不要与原 MMD2UE 模块同时安装。
2. 复制 `templates/retarget_pose.example.json` 到角色工作单目录。根据实际骨骼填上臂、肘、腕名称，填写两个重定向器路径。示例骨骼名不是自动映射结果。
3. `up_axis` 是该侧**组件空间**上方向。左右方向默认由两侧肩关节位置连线在水平面上的投影推导；可用 `left_axis` 显式指定。两侧分别校准，不假定 source/target 的局部轴一致。
4. 确认骨骼角色/坐标后设置 `reviewed: true`。在角色配置的 `pmx4ue` 下增加 `retarget_pose_profile`，值为此 JSON 的绝对路径。

在 PMX4UE 目录执行：

```powershell
python pmx4ue.py run --config "characters/MyCharacter/character.json" --stage retarget-pose
python pmx4ue.py run --config "characters/MyCharacter/character.json" --stage retarget-pose --execute
```

命令行方式在编辑器关闭时运行，避免同时写工程。没有 `--execute` 只显示计划；执行时会保存独立资产和 `retarget_pose.json` 报告，不能重复覆盖报告。迭代使用新工作单产物目录、新输出重定向器路径和新姿态名；也可以在已打开 UE 的 Python 中调用 `ue_retarget_pose.build(profile, namespace, report_path)`，不要同时运行外部写入进程。

## 手动微调

### 双侧腿部站姿匹配

选择一侧经审核的中立腿姿，分别测量左右髋→膝、膝→踝的单位方向，并转换到另一侧的组件坐标系。骨名映射正确仍不代表姿态已匹配。MMD2UE 本例两侧均 +X 向左、+Z 向上，允许直接使用方向；其它模型不能默认坐标一致。

对应侧配置 `leg_alignment`：

```json
{
  "legs": {"left": ["thigh_l", "calf_l", "foot_l"], "right": ["thigh_r", "calf_r", "foot_r"]},
  "directions": {
    "left": [[-0.02, -0.03, -1], [-0.016, -0.084, -1]],
    "right": [[0.02, -0.03, -1], [0.016, -0.084, -1]]
  },
  "left_axis": [1, 0, 0], "up_axis": [0, 0, 1],
  "max_foot_height_change_cm": 1
}
```

示例方向仅解释格式，实际值从审核的关节坐标计算。流程先转髋骨、再转膝骨匹配两段方向，最后反算踝骨局部偏移，保持脚掌原组件旋转，防止脚底随腿侧倾。禁止交叉腿、上指的站姿方向和超限脚高变化。手动 `edits` 在这些自动步骤之后执行，可有意覆盖结果。

报告 `stance` 记录髋/膝/踝的左右间距、脚踝高度、膝弯角与原生读回。它测量的是骨关节，不是鞋内缘；不能声称已经证明鞋面贴合或没有穿插。不同体型使用相同腿段方向后，踝间距仍可不同。脚位高度不能在固定骨长/上身条件下任意指定；超限需要单独审核，不自动移动 Root 或缩放骨骼。

### 先检查躯干基底

双臂水平不等于全身姿态合格。复制 `Default Pose` 也可能继承旧腰部修正，必须先比较躯干的参考/当前局部偏移和组件空间位置。确认参考躯干合理后，在该侧配置中加入：

**共用父骨变化时还必须审核下肢。** 只清理 Center/Waist 等上游偏移、保留旧 LegD/KneeD 补偿可能使下肢斜出。按当前模型实际角色审阅其后代偏移及最终髋膝踝方向，并将确认需要恢复的骨骼加入清单；不能套用全骨架清零。托洛洛的完整基底修正还包含 LegD_L、KneeD_L、LegD_R、KneeD_R，见 v3 决策记录。

```json
{
  "restore_reference_rotations": ["Center", "Groove", "Waist", "UpperBody"],
  "posture_checks": [
    {"start": "Waist", "end": "Neck", "up_axis": [0, 0, 1], "max_tilt_degrees": 2}
  ]
}
```

这是托洛洛的已审核例子，不是通用骨名或所有角色都适用的 2° 标准。Source 与 Target 分别判断；允许自然脊柱曲线，不把不同角色所有脊椎拉到一条直线。该检查只测量指定关节连线相对上方向的倾斜，不能代替侧视蒙皮外观和骨盆检查。

执行顺序：复制原姿态 → 恢复清单中的参考旋转 → 更新全局变换 → 自动对齐双臂 → 手动 edits → 躯干阈值/原生读回检查。不要把躯干复位写到最后的 `edits`，那会再次改变手臂方向。原根平移、局部位置与缩放保持不变。恢复旋转会正常影响后代的位置；不改蒙皮或骨骼层级。

报告新增 `restored_reference_rotations` 和 `posture.before/after/native_after`。任一最终躯干检查超限即失败；没有配置时保持旧版本行为。MMD2UE 复现实验入口为 `tools/ue_mmd2ue_tpose_v2.py`，见 `characters/TololoSchool1001/tpose-v2-decision.md`。

### 对齐后的局部微调

例如在自动对齐后，给目标手腕附加绕**当前骨骼局部 Y 轴** 5° 的旋转：

```json
{"bone": "Wrist_L", "mode": "add_local", "axis": [0, 1, 0], "degrees": 5}
```

加入对应侧的 `edits` 数组。只需要微调时把 `auto_arms` 设为 `false`，无需填写 `arms` 或方向。若以之前生成的重定向器作为输入，新修正在该侧当前姿态上累积，不从默认姿态重新开始。

精确替换偏移：

```json
{"bone": "Wrist_L", "mode": "set_offset", "quaternion_xyzw": [0, 0, 0, 1]}
```

这表示该骨骼回到参考局部旋转，不是世界旋转归零。UE 的组合规则是 `ReferenceLocalRotation × Offset`；脚本会处理世界修正到局部偏移的换算。

## 验收

打开输出重定向器，在 Source / Target 的 Current Retarget Pose 中选择生成的姿态名，使用 UE 原有 Edit Retarget Pose 功能继续编辑。分别看正面、侧面、掌心；再播放用户提供的走路/抬臂/转身动画。若 Op Stack 的 Retarget Pose 操作、Profile 或覆盖项指定了其它姿态，需同步选择新姿态；本工具不重写这些操作配置。

报告包含：修改前后完整骨骼数据、实际修改名单、各臂段对齐误差、UE 原生结果与计算预测的最大位置/旋转误差。未通过时状态为 `failed_do_not_use`，部分新资产保留用于排查，不可作为验收版本；原资产不覆盖。

数值检查默认上限为 0.01 cm / 0.05°，这只是读写一致性检查，不代替动画效果验收。手动修正可有意偏离 T 型，因此报告同时区分自动对齐误差与最终角度。

开发验证：`maintenance/ue_retarget_pose_smoke.py` 在独立工程使用同一 Rig 的 Source/Target 验证保存与重载；这不代表不同角色的动画重定向已验收。当前实测见 `VERIFICATION.md`。
