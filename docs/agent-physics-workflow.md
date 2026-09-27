# Agent 主导的物理迭代与验收

先读 `skills/pmx-to-ue/SKILL.md` 和 `references/physics.md`。本文补充已生成物理资产之后的操作闭环，不取代 PMX 语义盘点。新角色仍须从自己的 PMX、权重、骨架和动画出发。

## 1. 锁定测试对象，避免改错资产

记录 project、mesh、skeleton、各分区 PA、最终 ABP、动画、配置/代码版本及文件指纹。识别最终使用的 ABP，而不是中间生成蓝图。修改动画、PA、节点参数或依赖文件后，旧验收不能直接沿用；纯说明文档变动不要求重跑 UE。

托洛洛当前参考：`/Game/Characters/TololoSchool1001/PhysicsSandbox/Performance/ChestFollow_v1/ABP_ChestFollow_Travel`，mesh 为 `SK_TololoSchool1001_UpperOnlyCm_v1`。它是已被用户认可效果的参考，不是通用默认。胸部两个体改为跟随动画而非独立模拟，这是效果取舍，不能宣传成“胸部弹性优化”。

先分清任务：用户只要更新流程时，修改本工作台的说明/离线工具，不重新生成 UE 资产或启动高负载跑分。用户要求调整模拟时，再建立有版本的独立候选。

## 2. 更换测试动作，不绕过物理

1. 复制当前已认可的最终 ABP，使用新版本/动作后缀。保留原资产。
2. 确认新动画属于目标 skeleton；其它源骨架动画先经过已验证的 Source/Target 重定向器导出。不要为此改 mesh 或骨架。
3. 打开副本的 **My Blueprint → AnimGraph**，找到原动作的 Sequence Player，更换 **Sequence**。保留后续空间转换、物理节点及连线；循环动作按需开启 Loop Animation。
4. Compile 后核对实际 Sequence、目标 mesh 和全部物理节点/PA 路径。先看动作无物理对照是否正常，再判断模拟。
5. 场景角色保持 **Use Animation Blueprint**，Anim Class 指向测试副本。直接使用 Use Animation Asset 会绕过该 ABP 内物理，不能作为物理测试。
6. 保持播放速率 1。比较动作时不要同时改求解预算；低帧率测试要降低真正的更新频率，不是调慢播放速率。

自动化时可复制资产后替换 Sequence Player；必须发现并记录节点数量，多入口/状态机不得盲目替换全部。适配后在 UE 新版本资产上验证。当前角色脚本仍含专属骨名与路径，不宣称它已通用。

## 3. 根据症状选择最小实验

| 观察 | 下一步 | 不应采取 |
|---|---|---|
| 无物理也肢体分离/姿态错 | 回到动画/重定向/层级检查 | 调物理参数掩盖 |
| 移动或循环时衣物飞离 | 区分 root、pelvis/Center 轨道、组件位移；比较模拟空间与运动输入 | 每圈强制复位 |
| 裙子被外套专用臀部体顶起 | 查具体 shape 的双向 mask 与所属分区 | 膨胀衣服、添加衣裙避让 |
| 胸部/附件幅度不合适 | 根据效果目标做独立参数或跟随动画候选，说明语义差异 | 把角色专属决定推广给所有模型 |
| 帧率低且无物理对照也低 | 检查测量一致性、线程、窗口状态和环境 | 直接砍迭代或降低画质 |

每个候选只改变一个可解释因素。恢复策略只用于明确的传送/重置事件，不能替代连续运动的正确求解。Deferred 一帧延迟、频率/迭代取舍均须记录并看效果。

## 4. 四类证据独立验收

| 类别 | 最少检查 | 不能推出的结论 |
|---|---|---|
| 数值 | 静止、动画内部位移/循环、组件连续位移转向，60/30/15Hz 与 100ms 卡顿；有限变换/包络 | 指定 dt 通过不等于真实低帧率画面通过 |
| 碰撞 | 源 PMX 双向 mask、同骨多 shape、各分区映射及运行时抽查 | 分组号不同不等于隔离；有锚点不等于允许碰撞 |
| 视觉 | GameViewport 不同步态/角度采样，转身急停和低帧率连续观察 | 单帧看起来好不等于无穿插；截图请求成功不等于文件有效 |
| 性能 | 无物理对照与候选重复三轮，真实尺寸/画质/硬件，均值和 P99 | 小视口高 FPS 不等于 1080p/打包/多角色通过 |

接受状态分别填写 `measured / agent_reviewed / user_approved / pending / failed`，不要合并成一个布尔“通过”。没有精确穿透测量时明确写“采样未见明显异常”。记录每项原始报告、资产身份和退出码。

## 5. 有效性能测量规则

- 自有临时编辑器、当前目标工程的临时场景；不占用/关闭用户编辑器，不保存测试关卡。Windows 隐藏启动。
- 每项预热至少 8 秒、计时至少 20 秒，控制/候选各至少三轮且条件一致；推荐交替执行以观察环境漂移。
- 测前设置并回读 `t.MaxFPS 200`；记录 VSync、后台节流、实际 viewport、渲染比例/动态分辨率、RHI、画质及硬件。临时设置结束恢复。专门的 30/15FPS 稳定性实验单独记录，不混入不限速性能数据。
- 目标默认平均 ≥70 FPS、P99 ≤16.67ms。若平均与真实观察帧率差异 ≥10%，测量无效。无物理基线异常时不归罪求解器。
- 隐藏窗口渲染不正常可在自有实例用 `-RenderOffscreen` 对照；报告明确标注离屏。不要顺手改 DDC/RHI/画质。磁盘/缓存告警记录为环境问题，不凭共现认定因果。
- 截图必须来自运行中的 **GameViewport**；记录它的实际宽高。HighResShot 的截图尺寸不是跑分尺寸，截图放在计时区间外。检查文件存在且画面确为正在运行的角色。
- 计时报告写完后，仍需等待自有进程正常退出；退出崩溃/缺失结果不能验收。完整报告和进程退出码必须同时存在。
- 若用户允许其他高负载程序并行，不强行要求关闭；做同条件对照并判断数据有效性。异常时保留现场，说明局限，不终止用户程序。

### 离线复核工具

`tools/review_physics_benchmark.py` 支持历史采集器与新的 `ue_physics_performance.py` 的 `tests[]` 报告，不启动 UE、不改资产。运行器 `performance` 已自动连接通用采集和复核；采集依赖当前计划与对应的新进程数值报告，设置实际 PIE viewport 并逐帧回读。其它采集器需显式适配，不能拼接字段假装兼容。

```powershell
python tools/review_physics_benchmark.py "D:/UEProjects/MMD2UE/Saved/PMX4UE/PhysicsAcceptance_Offscreen_v3/report.json" --candidate ChestFollow --control NoPhysics --process-exit-code 0 --output "D:/UEProjects/MMD2UE/Saved/PMX4UE/PhysicsAcceptance_Offscreen_v3/review-v1.json"
```

退出码参数必须来自实际启动进程；上面 0 是该历史实测的值，不是允许给失败实验填 0。输出文件已存在时拒绝覆盖。默认要求 viewport 至少 1920×1080；支持 `--target-width/--target-height` 声明实际产品目标，不得事后降低目标掩盖失败。

- `invalid_measurement`：数据/过程不满足有效性检查，先修测试。
- `control_below_budget`：控制也未达到预算，先分析公共瓶颈。
- `candidate_below_budget`：有效测量中候选至少一轮超预算。
- `measured_scope_pass`：只在记录的条件内通过。

CLI 仅在 scope pass 且 viewport 达到请求尺寸时返回 0，否则返回 2；这不是“生产验收通过”。工具不会从原始 FPS 推断视觉质量或完整依赖未变，也不会把 viewport 尺寸当内部渲染分辨率。

## 6. 当前证据与下一步

托洛洛实测见 [physics-acceptance-v2-decision.md](../characters/TololoSchool1001/physics-acceptance-v2-decision.md)：最新物理版三轮 122.5–123.4 FPS，P99 11.76–12.64ms，**655×325 离屏单角色**；用户在本轮对效果反馈“不错”。缺少 1080p、耐久、多角色/LOD、完整接触与真实角色移动集成验收。不可把这些留空项写成已完成。

交接使用 `templates/physics-agent.md` 并填写 `templates/handoff.md`。优先补用户下一步最关心的动作/场景，不重复跑已证明无关的骨骼导出或腿骨清理。
