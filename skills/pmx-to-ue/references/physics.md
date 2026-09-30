# PMX 物理与性能

已有资产的迭代、换动画、验收与交接，继续阅读 [Agent 物理工作流](../../../docs/agent-physics-workflow.md)。新项目见 [执行手册](../../../docs/fresh-project-runbook.md)。运行器已接通通用采集与复核，角色专用脚本仅作历史证据。

## 当前实现是什么

PMX rigid bodies / spring joints → 审核后的分区清单 → UE Physics Asset → 原生 RigidBody 动画节点 → 已有骨骼蒙皮。运行时是 Chaos RBAN 刚体求解，不是 Chaos Cloth 顶点布料，也不是自己重写的布料求解器。自定义 `FAnimNode_PmxFilteredRigidBody` 继承 UE RigidBody，补上 PMX 每个 shape 的碰撞过滤。

不用 Blender 提前烘焙整段布料动画。Blender 在这里读取 PMX 数据并做坐标转换，运行时在 UE 中模拟。Bullet 与 Chaos 参数语义并不完全一致，保留源参数、记录换算和近似，并由动作对照验证；不可声称逐帧完全复刻 MMD。

## 从裙子开始的路径

1. `physics-inventory` 只读 PMX，输出全部骨骼、刚体、关节、源文件哈希、mask 语义。
2. `tools/draft_profiles.py --config <工作单>` 生成未审核 rig/physics 草稿。agent 根据刚体名称、关联骨、位置、group/mask、关节连通性识别裙子/外套/头发，填写 `partitions`。不要套用固定 group 编号。
3. physics profile 指定 `mesh`、PMX→UE `bone_map`、至少三个非共线 `landmarks`、稳定的 `measurement_anchor`、同骨架 `test_animation`。可明确允许同名映射，但不能假定日文 PMX 名与英语导出名一致。
4. `physics-inspect` 从 UE 实际 mesh 读取骨架和组件空间缩放，不能用 Blender 的猜测替代。`physics-plan` 验证所有动态刚体有归属或有原因的忽略，输出可执行计划。
5. `physics-build` 在独立路径生成各分区 PA、静止/走路 ABP 和性能对照 ABP，不修改角色 mesh/skeleton。`physics-test` 在新进程测量静止、步行和组件移动；然后 agent 看视觉表现。
6. 裙子通过后逐步增加外套、头发等分区；每次新增一个可解释变量，保留上版对照。

每个 partition 最少有 `name`、`purpose`、`dynamic_ids`；也可用已审核的 `dynamic_name_regex`。`ignored_dynamic` 为 ID→原因，例如阶段一尚未启用的头发。不得静默忽略不支持数据。

## 碰撞体与动态服饰必须分清

mmd_tools 已把 PMX 排除掩码转换为允许位。仅当 A.mask 允许 B.group **且** B.mask 允许 A.group 才可碰撞。不同 group 不代表必然隔离。

同一 pelvis 骨可能挂多个 shape：人体用小碰撞体、外套用大臀部碰撞体，它们的 group/mask 不同。保留 per-shape 过滤；不能把它们合并成整个骨骼的一条通用碰撞权限。某 shape 为关节锚点而保留不等于它要和裙子碰撞。

当前跨分区策略是 `cross_partition_collision="none"`，必须写 `cross_partition_reason`。若源数据确实允许跨动态组碰撞，隔离是明确的策略差异；计划中会记录被禁用的对数，不能声称无损还原。用户要求保留这种交互时，应合并有耦合的分区或实现经验证适配，不能偷偷丢失关节。不能额外加裙子/外套避让、膨胀、代理碰撞体。

## 当前需适配的情况

mode 2、无绑定刚体、一根 UE 骨被多个动态刚体驱动、不对称角限、跨分区关节、重复 PMX 骨名、同骨多 shape 材质语义冲突等会阻止计划。先分析语义，在本仓库新增适配与回归测试；不要调小刚度绕过结构问题。mode 0 作为跟随动画的碰撞体/锚点，mode 1 作为动态驱动。

没有同骨架动画时，设置 `rest_only=true`、空 `test_animation`、`performance_test.enabled=true`，生成静止 ABP、无物理和同步对照，先做静止数值与真实 PIE 静态性能测量；报告明确移动与游戏性能待验收。有源动作时先 `animation-export`，再建新动态版本并**重新跑动态性能**。静态跑分不能复用为动态通过；缺输入时不伪造走路动画或通过标记。`physics-plan` 对静态和动态都拒绝关闭性能的配置。

## 已有优化经验如何复用

性能不足时先按 [物理性能优化决策手册](../../../docs/physics-optimization-playbook.md) 建立同条件基线，再逐项改动和判退。该手册只提供可迁移的判断顺序，不预设某个角色的参数。

`draft_profiles.py` 提供候选 nonlinear 8 次 position iterations、60 Hz fixed time step。它不是每个模型的标准答案。旧配置不填 solver 时仍是同步 120 Hz / 16 次，便于兼容对照。

进一步启用 `simulation.timing="deferred"` 必须 `accept_one_frame_latency=true`：使用前帧结果换取调度优势，明确接受一帧延迟后再用。不要用更松碰撞/降画质冒充纯性能优化。

`performance` 的同场景对照：无物理 → 同步控制 → 候选，整组交替重复至少 3 次。每次设 `t.MaxFPS 200` 并回读；记录 VSync，结束恢复之前上限。不关闭用户会话。平均目标默认 ≥70 FPS，P99 ≤16.67ms；帧 cap、实际帧率、case 完整性、实际视口及进程退出均参与判定，输出 `performance_review.json`。低于预算、测量无效或视口不足会使该阶段失败，保留原始报告供诊断；不能靠静态数值测试或小视口截图跳过。静态 pass 只覆盖静态求解开销，不代表走跑/根运动/多角色或打包游戏性能。

数值测试通过、视觉认可、PIE 性能、打包游戏性能分别记录。项目可能被渲染/其它 GameThread 工作限制，先看无物理基线和线程耗时再改求解参数。原工程曾发生报告写完后编辑器退出崩溃，所以运行器仍以进程返回码判定执行失败，不吞错误。若复现，用自己的空白测试场景定位关闭时序，不修改用户生产场景。

## 根运动与循环位移的新增验收项

不能只测忽略根运动的原地动画。检查位移究竟在真实顶层 root、Center/pelvis 轨道还是组件上，分别测试动画内部前进/循环跳回、组件连续移动、15/30/60Hz 和卡顿。固定步长测试不要用浮点余数制造微秒末帧。仅勾选 Enable Root Motion 不能提取非根骨轨道上的整体位移。

在组件内部前进的骨架，可对照原生 Base Bone Space（选择适当的非模拟动画骨）、局部阻尼与世界阻尼的区分、运动速度/加速度上限；不要靠每次循环强制 reset 或添加衣裙代理碰撞修正。保持源 PMX 分组及 PA 不变，先在新 ABP 验证。托洛洛 Motion_v3 的测试与限制见 `characters/TololoSchool1001/physics-motion-v3-decision.md`；后续 ChestFollow 数值与小视口性能结果见 `characters/TololoSchool1001/physics-acceptance-v2-decision.md`。用户认可效果不替代完整游戏验收。这些不是所有模型的通用默认值，也不替代真正的 CharacterMovement 根运动集成。

性能测量前记录并行负载，不关闭用户应用来制造测试环境。用户允许直接测试时可以进行同条件对照；依据数据一致性判断有效性，不因用户正在游戏一律停工。游戏 dt 与观察帧数明显不一致的测试不能验收；无物理对照也异常时，先排除环境干扰，不能据此宣称求解器出现性能雪崩。必须记录实际 viewport 和渲染配置，HighResShot 尺寸不是跑分尺寸；窗口不可见导致测量异常时可用自有离屏实例对照，标明限制。
