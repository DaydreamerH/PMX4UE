# 物理可用性评估（2026-09-27，未提交）

后续复测已获得有效离屏渲染结果，参见 [v2 复测结论](physics-acceptance-v2-decision.md)。本文件保留当时失败测量的原始记录；下文编辑器视口截图不作为运行时动态验证证据。

结论：ChestFollow_v1 可继续作为试用候选，**尚不能标记游戏生产可用或稳定 60 FPS**。本轮不修改物理参数、mesh、骨架、PA、ABP、动画或场景；仅增加只读诊断及改进性能测量脚本。

## 最新资产与动态数值

目标 `Performance/ChestFollow_v1/ABP_ChestFollow_Travel`，以上次静态生成/重载报告的源与输出哈希为输入身份。胸部两个体跟随动画，取消独立模拟，不是弹性减幅。

使用 `tools/ue_mmd2ue_physics_acceptance.py`；正常权限命令行进程退出 0。输出 `Saved/PMX4UE/PhysicsAcceptance_v1/numerical.json`，日志 `Saved/Logs/PhysicsAcceptance_v1_Retry.log`。

| 20 秒场景 | 裙骨相对骨盆最大包络半径 |
|---|---:|
| 动画内部前进，60Hz | 34.21 cm |
| 动画内部前进，30Hz | 34.56 cm |
| 动画内部前进，15Hz | 35.51 cm |
| 动画内部前进，60Hz + 100ms 卡顿 | 34.21 cm |
| 动画前进叠加组件连续移动，15Hz | 38.23 cm |
| 动画前进叠加组件连续移动，60Hz + 卡顿 | 37.68 cm |

六项均完整执行，无 NaN/非有限变换，442 模拟骨、330 shape 过滤、0 过滤映射错误。两个节点保持 LowerBody Base Bone Space / Deferred。前后资产哈希一致。t.MaxFPS 设置并回读200，退出恢复0。没有增加周期性复位。

包络半径不是皮肤/衣物接触穿透深度；边长比最大仍约5.59，指标未定位具体骨，不把它直接归因为蒙皮拉伸，也不能忽略后声称约束完全准确。本轮未做站立长稳态、精确接触深度、碰撞掩码逐对运行时抽查、30分钟耐久、LOD切换或CharacterMovement集成验收。

## 带渲染性能：无效，未验收

用户允许直接开始。独立隐藏测试编辑器、模板场景、不保存关卡、不改画质。计划 NoPhysics / Baseline6 / ChestFollow 各重复三次；t.MaxFPS200、VSync0。读取当前引擎源码后仅在该进程通过命令行 EditorSettings 覆盖关闭后台CPU节流，读回为false；没有修改物理求解预算。

`PhysicsAcceptance_PIE_v2/report.json` 已完成的观察帧率分别为 NoPhysics 1.85、Baseline6 1.95、ChestFollow 2.05、第二轮 NoPhysics 2.00 FPS。游戏dt推算约2.52–2.57 FPS，与真实观察帧数不一致，全部 measurement_valid=false。不能用这些数字判断物理开销，更不能据此选择减迭代候选。

同时日志持续出现 ZenLocal HTTP 507 Insufficient Storage；只读检查C盘约剩2.12GB（十进制），D盘约58.5GB。这是明确的环境异常，但**尚未证明它是约2FPS的直接原因**。即使用户的游戏通常不影响测试，也不能在当前不一致的数据上给出60FPS结论。后台节流读回已关闭，仍需定位渲染/窗口状态/系统争用或测量路径。

在第四项后向本轮唯一自有实例 PID28952 请求正常关闭，未结束其它应用。进程最终返回 -1073741819（访问违规），不能算正常完成；report没有completed状态，不改写原报告伪造完成。后续为诊断脚本加了无效测量自动退出路径，便于先卸载回调并恢复帧上限，该自动退出路径尚未实测。

两个截图显示角色、裙子和外套仍跟随，未见整体飞离；但低帧率单帧不能证明动态无穿插或胸部观感通过。截图 `Saved/MMD2UECaptures/PhysicsAcceptance_PIE_v2_1_Baseline6.png` 与 `_2_ChestFollow.png`。

## 失败尝试保留

- 首次数值启动受缓存不可写阻止，未进入测试，`PhysicsAcceptance_v1.log`。正常权限重试成功；未使用 ForceMemoryCache 或替换缓存配置。
- PIE v1 用不存在的Python属性别名读取编辑器性能设置，测试未开始；改为反射C++属性名后v2读取成功。v1进程虽退出0仍不是测试成功。

## 下一步

先获得正常的无物理渲染基线并解决测量一致性；必要的磁盘清理/缓存迁移另经用户确认，不能自行删除。然后重复三轮同场景对照，平均≥70 FPS、P99≤16.67ms才作为单角色性能候选，再补胸部动态、衣物接触、真实角色移动和打包游戏验收。暂不降低精度、不自动替换已认可场景。
