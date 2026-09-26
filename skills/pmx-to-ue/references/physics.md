# PMX 物理与性能

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

没有同骨架动画时，现包装器不能完成 build/test 全链；agent 可以实现独立 rest-only 分支，或先等待合适动画。缺输入时不伪造走路动画、验收数据或通过标记。

## 已有优化经验如何复用

`draft_profiles.py` 提供候选 nonlinear 8 次 position iterations、60 Hz fixed time step。它不是每个模型的标准答案。旧配置不填 solver 时仍是同步 120 Hz / 16 次，便于兼容对照。

进一步启用 `simulation.timing="deferred"` 必须 `accept_one_frame_latency=true`：使用前帧结果换取调度优势，明确接受一帧延迟后再用。不要用更松碰撞/降画质冒充纯性能优化。

`performance` 的同场景对照：同步控制 → 候选重复 3 次 → 无物理控制。每次设 `t.MaxFPS 200` 并回读；记录 VSync，结束恢复之前上限。不关闭原项目中的用户会话。平均目标默认 ≥70 FPS 留余量，P99 ≤16.67ms；帧 cap、观察到的帧率、case 完整性均参与判定。

数值测试通过、视觉认可、PIE 性能、打包游戏性能分别记录。项目可能被渲染/其它 GameThread 工作限制，先看无物理基线和线程耗时再改求解参数。原工程曾发生报告写完后编辑器退出崩溃，所以运行器仍以进程返回码判定执行失败，不吞错误。若复现，用自己的空白测试场景定位关闭时序，不修改用户生产场景。
