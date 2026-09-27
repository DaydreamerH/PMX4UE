# Motion_v3 的性能候选：MotionPerf_v1

2026-09-27，未提交。用户认可 Motion_v3 效果，要求提升不足60FPS的性能。

## 最小改动

在 MMD2UE 新目录 `/Game/Characters/TololoSchool1001/PhysicsSandbox/Performance/MotionPerf_v1/` 生成：

- `ABP_Skirt6Outer4_Travel`：裙子6次、外套/头发分区4次 position iterations。
- `ABP_Both4_Travel`：两分区均4次。
- `ABP_Both3_Travel`：两分区均3次。
- `ABP_NoPhysics_Travel`：相同最新动画的无物理对照，不作为推荐资产。
- `ABP_Build_*` 仅为生成中间资产，不应拿来代替最终候选。

候选均维持60Hz nonlinear、Deferred、LowerBody Base Bone Space、DampingAlpha0及Motion_v3运动上限。不删骨/刚体/关节，不改PMX分组、mask、蒙皮、材质、原动画或已有场景。源文件哈希检查通过。降低迭代是精度/收敛预算的取舍，不能称为完全无损。

## 已执行与证据边界

`tools/ue_mmd2ue_motion_performance.py` 在原生UE中生成、重载并执行12项12秒测试：基线及3候选 ×60Hz/15Hz/60Hz夹100ms卡顿。全部有限、完整运行，444模拟骨骼、330 shape过滤、0过滤映射错误；裙骨距骨盆最大包络均低于36cm。这不是接触穿透深度，也不替代动态视觉验收。

报告 `Saved/PMX4UE/MotionPerf_v1/numerical.json`；命令行进程exit0。该时段用户另有游戏运行，耗时数字不可作为公平性能对照。数值测试证明给定dt下没有裙子远离角色的失稳，不证明60FPS。

`tools/ue_mmd2ue_motion_performance_pie.py` 为复制后适配的真实渲染测试：同一模板场景、最新带Center位移动画、相机跟随骨盆、预热8秒测20秒、t.MaxFPS200回读并恢复。不保存场景、不改画质。检查实际观察帧率与游戏dt推算帧率一致性。

`Saved/PMX4UE/MotionPerf_PIE_v1/report.json` **性能无效**：用户明确正在打游戏；无物理对照也异常，仅约2实际FPS。Both3偶然约79FPS不能宣称提速或达标。编辑器最终正常退出。

v2试图排除后台节流时，Python未暴露EditorPerformanceSettings，启动报AttributeError，未进入测量、未改设置，编辑器正常退出。该未验证适配已撤回。v1异常不能被归因为后台节流或物理补步；二者均只是排查假设。

## 接手与下一步

用户正在游戏，暂停所有高负载测试，不关闭用户游戏。候选保持独立，未替换已认可Motion_v3。

待用户确认可测试后，先确认没有UE进程，再在自有临时编辑器中执行PIE脚本，环境变量选择新 `PMX_MOTION_PIE_RUN`，`PMX_MOTION_PIE_CASES=NoPhysics,Baseline6,Skirt6Outer4,Both4,Both3`、`PMX_MOTION_PIE_REPEATS=3`、`PMX_MOTION_PIE_CLOSE=1`。不要覆盖旧报告。Windows用Hidden启动，正常RHI/画质；观察世界dt与wall时序，异常先诊断环境。

选择平均≥70FPS且P99≤16.67ms候选，再补连续组件运动和长时间低帧率检查，并由用户复核动态效果。未达标则继续定位求解/渲染/调度成本；不能靠锁Center或放宽碰撞掩码提速。本轮尚无可宣布达标的性能结论，也未做打包游戏验收。
