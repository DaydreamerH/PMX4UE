# T Pose v3：补齐下肢旧偏移清理

日期：2026-09-27，未提交。

## 观察与原因

用户认可 v2 上半身，但截图双腿斜向后方。保存数据确认：Center/Groove/Waist/UpperBody 已恢复参考旋转，两侧 LegD 仍继承约 41.53°、KneeD 约 2.13° 的旧姿态偏移。共用父骨旋转改变后，这些下肢偏移不再适用于当前基底。这是 v2 审核不完整，不是 mesh/腿骨层级故障。

## 改动

从 v2 复制新 RTG，仅恢复 `LegD_L / KneeD_L / LegD_R / KneeD_R` 四个 Retarget Pose 旋转偏移。沿用通用 restore_reference_rotations，不新增求解器。没有对整个 skeleton 清零，不改普通 leg 链、骨架结构、绑定、Root Motion、物理或动画。Source 不改；上半身不重算。

输出：`/Game/Characters/TololoSchool1001/Rigs/TPose_v3/RTG_UEFN_To_Tololo_TPose_v3`。
Source 保留 `TPose_Source_v2`，Target 使用新 `TPose_Target_v3`。

## 实测

- UE 原生双侧髋到踝连线相对竖直向下：约 44.685° → 3.51348°，恢复参考腿形，不强行消除自然倾斜。
- 目标非 D 腿子树的骨骼位置差 0 cm；旋转差在 0.000003° 浮点精度内。上身保持 v2 的结果，腰颈倾斜仍 0.570628°。
- Source 全部骨骼位置差 0 cm。76 项测试通过，含恢复腿部补偿但保留上半身的回归用例。
- 原 RTG、Rig、mesh、Skeleton 文件哈希检查通过。视觉和动画验收仍待完成。
- 生成及新进程重载均退出 0；重载骨骼位置与保存结果完全一致，当前姿态选择与原资产哈希检查通过。

## 复现与交接

使用 `tools/ue_mmd2ue_tpose_v3.py`，UE 编辑器关闭时通过现有 MMD2UE 的 Python commandlet 执行，与 v2 相同启动方式；环境变量 `PMX4UE_POSE_RELOAD=1` 执行只读重载验证。报告在主工程 `Saved/PMX4UE/RetargetTPose_v3/normalize.json`、`reload.json`。已有输出拒绝覆盖。

后续规范化更改共用父骨时，必须同时审核其上下肢后代的**已有姿态偏移及最终组件空间方向**；这不是再次检查腿骨导出是否变化。先明确清理范围并完成全身基底，再计算手臂。不应再把“上身直立、手臂水平”当成全身 T Pose 通过。
