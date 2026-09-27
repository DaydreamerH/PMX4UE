# 物理复测：数值与小视口性能通过（2026-09-27）

本次测试对象为 `Performance/ChestFollow_v1/ABP_ChestFollow_Travel`，动画为 `Animations/M_Neutral_Walk_Loop_F`，均位于 `/Game/Characters/TololoSchool1001/PhysicsSandbox/`。没有修改 mesh、骨架、物理资产、动画或正式场景；测试前后核对的七个源/候选资产哈希一致。诊断脚本和记录保持未提交。

## 结论及边界

最新版本通过本轮动态数值检查及离屏小视口单角色性能门槛；采样画面未见衣物整体飞离或上下身分离。**尚不等于 1080p 游戏、长时间运行、所有动作与无穿插验收通过。** 胸部两个体跟随动画，不是独立弹性模拟。

本记录更新 v1 中“未获得有效渲染性能”的状态。旧的约 2 FPS 结果仍是无效测量，不能作为物理开销依据。ZenLocal 存储告警仍存在，而本轮能得到有效高帧率，不能断言告警是之前低帧率的直接原因。

## 数值复测

报告：`Saved/PMX4UE/PhysicsAcceptance_v2/numerical.json`，测试进程正常退出 0。

六项各 20 秒：60/30/15Hz 动画位移、60Hz 加 100ms 卡顿，以及叠加组件连续移动/转动的低帧率与卡顿场景。全部完成，无非有限变换，442 个模拟骨、330 个 shape 过滤、0 个过滤映射错误。裙骨相对骨盆最大包络半径依次约 34.21、34.56、35.51、34.21、38.23、37.68 cm。未增加周期性强制复位。

这是指定时间步的数值测试，不是对应帧率下的视频验收。包络不是精确接触穿透深度；启动阶段最大骨边长比约 5.59，尚未定位具体骨，不能因此声称约束与蒙皮完全准确。

## 有效渲染性能

最终报告：`Saved/PMX4UE/PhysicsAcceptance_Offscreen_v3/report.json`。

使用 MMD2UE 的模板场景、真实跨骨架动画和最新物理 ABP，三轮交替无物理/有物理。每项预热 8 秒、测量 20 秒。`t.MaxFPS=200`、VSync=0、后台节流关闭；不调整渲染质量。使用 `-RenderOffscreen`，实际游戏视口 **655×325**，不是 1080p。报告状态 completed，六项 measurement_valid=true，计帧与时间步推算一致，进程正常退出 0，退出前恢复帧率上限 0。

| 轮次 | 无物理平均 FPS | 最新物理平均 FPS | 最新物理 P99 帧耗时 |
|---|---:|---:|---:|
| 1 | 140.12 | 122.55 | 12.64 ms |
| 2 | 133.12 | 123.42 | 11.76 ms |
| 3 | 134.54 | 122.83 | 11.87 ms |

三轮均达到平均 ≥70 FPS、P99 ≤16.67ms 的候选门槛。第一轮约 0.367% 帧超过 16.67ms，其余两轮为 0，因此不能表述为所有帧都超过 60 FPS。帧率差值也不能直接视为物理独占 CPU 时间。

## 画面证据和诊断修正

诊断脚本此前截取编辑器视口，不应当作为运行时画面证据；现改为 GameViewport 截图，并记录运行中的 LowerBody、LegD_L、Skirt_0_0 位置采样。v2 截图有模板 DefaultPawn 球体遮挡；v3 仅隐藏临时测试世界中这个 Pawn 的渲染，未改 PMX 碰撞。相机 FOV 为 55。

最终已检查不同步行阶段的全身图：

- `Saved/MMD2UECaptures/PhysicsAcceptance_Offscreen_v3_1_ChestFollow_phase1.png`
- `Saved/MMD2UECaptures/PhysicsAcceptance_Offscreen_v3_1_ChestFollow_phase2.png`
- `Saved/MMD2UECaptures/PhysicsAcceptance_Offscreen_v3_5_ChestFollow_phase2.png`

截图在计时区间之后拍摄，1000×1000 截图尺寸不代表性能测试分辨率。裙子、外套在采样中随步态变化，未见整体飞离；这些是离散截图，不是连续视频，不足以排除局部穿插。

## 尚待验收

固定 1920×1080 游戏视口或打包程序的同场景对照；连续视频和接触穿插检查；30 分钟耐久、转向急停、真实 CharacterMovement/Root Motion 集成、多角色和 LOD 切换。通过这些检查前保留“候选可用”，不标为全面生产通过。
