# T Pose v4：双侧站姿匹配

日期：2026-09-27，MMD2UE 原工程，未提交。

## 观察 → 决策

用户截图表明 v3 虽修复倾斜，Source 双腿仍明显外张。原生关节数据显示 Source 髋/踝间距 15.50/30.52 cm，Target 为 13.95/10.92 cm。不能以双臂水平或腿部偏移归零作为双侧中立姿态已匹配的证据。

采用 Target v3 已恢复的自然腿形为基准，分别匹配 Source 左右大腿/小腿方向；不将 Source 目标踝位置强塞到 Target 坐标，不缩放骨长/髋宽。Target 用相同方向验算，实质保持原姿态。两侧脚掌组件旋转保持不变，避免收腿造成脚底倾斜。不是把左右踝骨移到同一点，不宣称鞋内缘已经贴合。

## 实现与输入输出

通用 `retarget_pose_math.plan` 新增显式 `leg_alignment`。Pure FK + 最短弧旋转，将组件修正转为参考局部偏移；保留每个局部位置/尺度。读回仍使用 UE 原生 Retarget Pose。

- 脚本：`tools/ue_mmd2ue_tpose_v4.py`。
- 输入：`/Game/Characters/TololoSchool1001/Rigs/TPose_v3/RTG_UEFN_To_Tololo_TPose_v3`。
- 输出：`/Game/Characters/TololoSchool1001/Rigs/TPose_v4/RTG_UEFN_To_Tololo_TPose_v4`。
- 两侧当前姿态：`TPose_Source_v4` / `TPose_Target_v4`。
- Source 实际骨：thigh_l/r、calf_l/r、foot_l/r；Target：LegD_L/R、KneeD_L/R、AnkleD_L/R。
- 当前两侧组件轴已审核均 +X 向左、+Z 向上；其它模型必须显式转换，不能直接套用。
- 不修改 mesh、Skeleton、原动画、Rig、物理资产或操作栈。

## 验证证据

- Source 踝间距 30.52171 → 12.49731 cm；Target 保持 10.92118 cm。差值来自各自髋宽和骨长，而非方向仍外张。
- Source 膝弯角约 4.9607° → 3.1653°，与 Target 相同；脚踝高度下降约 0.324 cm，在审核的 1 cm 上限内。没有以脚高改变为由移动上身。
- 两侧非腿部子树位置差 0 cm；脚掌组件旋转数值误差 0°。
- 原生腿段方向误差均 < 0.000001°。78 项逻辑测试通过，覆盖旋转后的父坐标、骨长/脚掌/上身保持、重复执行、错误方向/层级/脚高超限拒绝。
- 生成与独立进程重载均退出 0；双侧重载位置差 0 cm，当前姿态选择、配置与原资产文件哈希检查通过。
- 生成报告：`D:/UEProjects/MMD2UE/Saved/PMX4UE/RetargetTPose_v4/normalize.json`。
- 运行使用 MMD2UE Python commandlet，编辑器关闭，新资产拒绝覆盖。`PMX4UE_POSE_RELOAD=1` 执行新进程重载验证，输出同目录 `reload.json`。

## 待审核与边界

视觉/动画尚未验收：查看双侧正面/侧面鞋底与膝盖，再播放行走和转身；骨骼方向一致不能证明蒙皮不穿插。既有 Root Motion 配置警告不在此次修正范围。Target 不是鞋面零间隙约束，本轮重点是解决源站姿外张与目标收拢之间的不一致。
