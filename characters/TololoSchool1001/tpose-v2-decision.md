# 托洛洛 T Pose v2：躯干基底修正

日期：2026-09-27。所有修改未提交。仅在 MMD2UE 原工程执行。

## 观察 → 假设

用户确认 v1 双臂已呈 T，但目标腰部后仰。v1 复制的原当前姿态包含 Center、Groove、Waist、UpperBody 的非单位旋转偏移，自动手臂算法保留了这些偏移。腰到颈连线偏离组件 Z 轴 13.965632°，水平位移 9.479970 cm；不能仅凭手臂方向宣布 T Pose 合格。

## 最小改动

只在新重定向器的目标命名姿态中，将四处旋转偏移恢复为单位四元数，随后重新计算上臂/前臂。Source 保留已验证的基底并重新验算。没有调用 UE Auto Align，没有更改 mesh、绑定姿态、骨架层级、原动画、物理、链映射或根运动配置。

通用工具新增显式 `restore_reference_rotations` 和关节连线 `posture_checks`，不内置角色骨名。托洛洛目标腰颈连线限值 2°；源 UEFN 骨盆到颈限值 5°（保留其原有约 4.19° 曲线）。这些是本实验审核阈值，不是跨模型默认规则。

## 输入与结果

- 输入：`/Game/Characters/TololoSchool1001/Rigs/TPose_v1/RTG_UEFN_To_Tololo_TPose_v1`
- 输出：`/Game/Characters/TololoSchool1001/Rigs/TPose_v2/RTG_UEFN_To_Tololo_TPose_v2`
- Source：`TPose_Source_v2`；Target：`TPose_Target_v2`，均已激活。
- 实际 Source mesh：`/Game/Characters/UEFN_Mannequin/Meshes/SKM_UEFN_Mannequin`
- 实际 Target mesh：`/Game/Characters/TololoSchool1001/PhysicsSandbox/SK_TololoSchool1001_UpperOnlyCm_v1`
- 复用 v1 已建立的实际 Source/Target Rig，不修改或重复生成 Rig。
- UE 原生目标腰颈倾斜：13.965632° → 0.570628°；水平位移：9.479970 → 0.371368 cm。
- 两侧臂段最大方向误差 < 0.000003°；最大原生/预测位置误差 < 0.000017 cm。
- Source 前后最大位置差 < 0.000000018 cm，属于数值精度范围。
- 75 项纯逻辑测试通过，含继承倾斜失败复现、先恢复躯干再对齐、幂等、清单校验。
- 独立新进程重载通过：位置差 0 cm；双侧当前姿态、链映射/操作开关正确，输入 mesh、Skeleton、Rig、v1 RTG 文件哈希均未变。

## 重现与核查

需先确认 UE 编辑器关闭；已有输出拒绝覆盖。此命令只后台生成数据，不用于画面/性能测试。没有修改工程 RHI、DDC 或画质设置。

```powershell
& 'D:/EpicGame/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe' 'D:/UEProjects/MMD2UE/MMD2UE.uproject' -run=pythonscript '-script=D:/UEProjects/MMD2UE/PMX4UE/tools/ue_mmd2ue_tpose_v2.py' -unattended -nosplash -NullRHI
```

重载核查：设置本进程环境变量 `PMX4UE_POSE_RELOAD=1` 后再次执行同一脚本，结束后移除此环境变量。报告：`D:/UEProjects/MMD2UE/Saved/PMX4UE/RetargetTPose_v2/normalize.json` 与 `reload.json`。记录输入资产哈希、输出哈希、配置、完整前后骨骼与数值检查。

## 边界与下一步

新资产的侧视蒙皮外观、行走/转身动画尚未视觉验收，不将原生读回通过当作视觉通过。进入新资产的 Editing Retarget Pose，分别选 Source/Target 检查侧面与手掌，再播放行走动画。v1 已有 Root 链/缺失根骨相关警告本轮不更改，与这次静态躯干偏移不是同一问题。手掌扭转匹配也仍非自动解决范围。

运行日志曾有 Zen DDC `Insufficient Storage (507)`，本次资产生成成功；未删除缓存或改变存储配置。如果后续启动反复编译，需要单独检查缓存磁盘空间。
