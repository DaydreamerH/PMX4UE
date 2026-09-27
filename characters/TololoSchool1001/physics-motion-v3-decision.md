# 根/骨盆位移下的物理稳定性：Motion_v3

2026-09-27；独立实验，未提交。用户已认可运动稳定性/效果，反馈不足60帧；后续性能实验见 `physics-motion-performance-v1-decision.md`。

## 观察与原因

用户反馈最新动画配性能 ABP 时裙子在持续位移下不稳定，低帧率恶化。旧 TestExperiment 强制 IgnoreRootMotion，加原地步行/组件移动不能覆盖此路径。

新进程采样实际 `PhysicsSandbox/Animations/M_Neutral_Walk_Loop_F`：4 秒动画中最顶层 `SK_TololoPmxCmNative_v2_Skeleton` 与 ParentNode 的局部平移均为零，Center 局部累计位移约 721.46 cm。这个动画的前进主要在 Center，而不是顶层根骨；仅勾选 Enable Root Motion / Force Root Lock 不能把 Center 的位移变成角色移动。这里的局部 Z 不是世界向上轴，不能误判为角色上升 7 米。

Component Space 下碰撞体跟随骨架在组件内部前进，动态体靠约束追赶；4 秒循环时骨盆突然跳回约 7.2 米。原生延迟输出又使用上一帧物理结果，出现大幅错位。实际复现旧方案在循环处裙骨距骨盆约 7.3 米，不是碰撞组缺失。Root-motion 重定向/提取问题仍独立存在，本轮不修改原动画或 v5 重定向器。

## 最小优化

从 `Performance/Perf_v3/ABP_Deferred6_60_Walk` 复制，改用最新动画，两个原生/PMX 过滤 RigidBody 节点均设置：

- Simulation Space = Base Bone Space，Base Bone = LowerBody（此模型非模拟的动画骨）。
- WorldAlpha = 1，保留世界运动响应。
- DampingAlpha = 0：PMX 局部线性/角阻尼仍在；不再将整个角色匀速位移作为同等强度的世界阻尼阻力。这是有意改变运动阻尼语义，不宣称完全复刻 Bullet。
- MaxLinearVelocity = 600 cm/s；MaxLinearAcceleration = 2000 cm/s²；MaxAngularVelocity = 6 rad/s；MaxAngularAcceleration = 40 rad/s²。只限制传入模拟的运动，不限角色移动速度。这些是本模型实验参数，不是全模型默认值。
- 保留性能版 Deferred、60Hz fixed step、6 次 position iterations。未添加复位逻辑，没有新增衣裙交互、代理碰撞体、改 mask 或修改 PA/mesh/skeleton。

UE 原生机制参考：[RigidBody 文档](https://dev.epicgames.com/documentation/unreal-engine/animation-blueprint-rigid-body-in-unreal-engine)。本机 UE 5.8.2 的 `FSimSpaceSettings` 注释明确区分 DampingAlpha 与局部阻尼；RBAN 原生执行 kinematic target 更新和物理子步，本轮不重写求解器。

## 产物

内容路径前缀：`/Game/Characters/TololoSchool1001/PhysicsSandbox/Performance/Motion_v3/`。

- 推荐复核：`ABP_BoneBoundedDeferred_Travel`，最新带位移动画。
- 同步对照：`ABP_BoneBounded_Travel`。
- 旧空间对照：`ABP_ComponentDeferred_Travel`。
- `InPlace` 后缀仅作原地动画 + 持续组件移动的独立测试，不替换用户原动画。

本轮不自动替换用户场景中的 ABP，也不修改原性能资产。源模型/动画/ABP/PA 哈希检查通过。

## 实测

32 个八秒组合：同步/延迟 × 旧组件空间/候选骨盆空间 × 动画内部位移/原地动画加连续组件运动 × 60/30/15Hz/60Hz夹100ms卡顿。

| 动画内部位移，延迟版 | 旧版裙骨最大骨盆相对距离 | 候选最大距离 |
|---|---:|---:|
| 60Hz | 736.79 cm | 34.21 cm |
| 30Hz | 733.32 cm | 34.56 cm |
| 15Hz | 728.11 cm | 35.51 cm |
| 60Hz夹100ms卡顿 | 736.79 cm | 34.21 cm |

这是裙骨到骨盆的包络距离，不是接触误差或蒙皮穿透深度。旧版超 500 cm 后中止；候选完成八秒。候选新进程重载后另做 20 秒多循环：15Hz 动画位移 35.51 cm；60Hz夹卡顿 34.21 cm；15Hz连续组件移动 42.61 cm，全部完整执行，无 NaN，444 个模拟骨骼，过滤映射错误 0。无周期性 ResetDynamics。

合成 dt 用来测试帧率敏感性，不是实测游戏帧率。测试前设置并回读 `t.MaxFPS 200`，结束恢复。60Hz 动画位移例中旧延迟版动画/物理提交及等待均值约 5.61 ms，候选约 6.84 ms；这不包括渲染，也不是总异步物理 CPU 成本，不能宣称整个游戏已达到 60 FPS。候选可能因接触更有效而比旧失稳状态多耗时。

## 限制与复现

- 入口：`tools/ue_mmd2ue_physics_motion_v1.py`（工具 v1，最终输出命名空间 Motion_v3）；复核：`tools/ue_mmd2ue_physics_motion_reload.py`。需要 MMD2UEEditor 中本轮 `MMD2UEPhysicsMotionTools`，未复制整套插件，尚未作为通用 PMX4UE 默认接口发布。
- 主工程报告：`Saved/PMX4UE/PhysicsMotion_v3/report.json`、`reload.json`；对应日志 `Saved/Logs/PMX4UE_PhysicsMotion_v3*.log`。
- Motion_v1 探针漏统计原生裙节点，被444骨骼检查拦下；Motion_v2 含浮点余数造成的极短末帧，不能用于低帧率验收。最终工具已覆盖两类节点，并拒绝制造微秒末帧。旧实验保留但不推荐使用。
- 当前验证是未提取的动画骨骼位移和合成组件运动，不是 CharacterMovement 提取真正根运动的游戏集成测试。
- 没有测量精确 shape 穿透/接触数；骨边长度仍有偏差，数值稳定不代表所有局部穿插消失。视觉与实机 PIE/打包性能待验收。
- 原动画位移迁移到真实根骨或由 CharacterMovement 接管是单独后续项，不应在此轮通过改 mesh 或锁 Center 来掩盖。
- Editor 模块编译成功，78 项既有逻辑回归通过；本轮主要验证为真实 UE 原生求解对照，既有测试不是新增动态稳定性单元测试。
