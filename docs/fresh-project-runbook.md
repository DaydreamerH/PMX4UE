# 从 PMX 开始：新项目执行手册

这是 agent 的执行顺序，不是要求用户手工逐项配置。新 agent 先完整阅读 `AGENTS.md`、`skills/pmx-to-ue/SKILL.md` 和对应领域参考。用户提供 PMX（含引用贴图）、目标 `.uproject`；若需动态验收，另提供可用源动画与其骨架。工具不会下载第三方角色/动作。

## 迁移范围

复制整个 PMX4UE 工作台的源码、docs、templates、skills、presets、tests、unreal；不需要 `.local`、缓存、测试产物或历史项目的 Saved/Content。`maintenance` 和 `tools/ue_mmd2ue_*` 是显式历史案例，不是通用入口，不能直接用于新角色。目标工程缺少 MMD2UE 时使用独立 PMX4UE 插件；二者不能同时加载。

先按 README 打包/安装与目标 UE 匹配的插件。当前验证 UE 5.8.2、Blender 3.6.23+mmd_tools、Python 3.10+。工具路径、源单位、角色 ID 由本机证据确定，不复制本机 D 盘路径。

## 执行顺序

所有阶段通过 `python pmx4ue.py run --config <工作单> --stage <阶段>` 预览，加 `--execute` 才执行。先用 `init` 生成配置，再 `doctor` 和 `capabilities`：前者查路径，后者在 UE 中验证实际加载接口，不能互相替代。

| 阶段 | agent 要完成的判断/产物 |
|---|---|
| audit → export | 审核单位、贴图完整性；源 PMX 只读，厘米 FBX，manifest 保留 PMX 原名→导出骨名 |
| skeleton-audit | 骨骼语义、权重、共同祖先；默认 preserve，不清理腿骨 |
| skeleton-plan → skeleton-apply（可选） | 有证据才选择 upper-only；独立输出，不覆盖原 mesh |
| material-draft → material-check | 审核槽、贴图用途、透明/双面/风格，不把建议当事实 |
| ue-build → ue-validate → material-compile | 新 namespace 导入；槽/参数/纹理检查，再实际 RHI 材质编译；agent 看画面 |
| face-sdf（可选，脸部 SDF 材质已有时） | 审核头骨、参考双轴、槽与 provider，生成独立材质/预览 BP；按 face-sdf-runtime.md 验证真实动画跟随 |
| physics-inventory → draft_profiles.py | 读取 PMX 原始刚体/关节/双向 mask；生成未审核 IK/物理档案 |
| ik → 姿态采集/模型与配对方案 → retarget-pose → 新进程重载 | 双侧真实不同骨架，角色语义驱动；详见 agent-retarget-workflow.md |
| animation-export（有动作时） | 用审核后的 RTG 输出新动画，保留源 root-lock/轨道；再看目标角色动作 |
| physics-inspect → physics-plan → physics-build → physics-test | 独立 PA/ABP；新进程静止/移动/低频/卡顿测试；看衣物与碰撞 |
| performance（有动作时） | 三轮交替无物理/同步/候选、真实视口、退出码、哈希和独立验收报告 |

`draft_profiles.py --config <工作单>` 要求已有 manifest 和 physics inventory。骨名映射来自导入元数据，不猜日英对应；重复 PMX 名被剔除并要求适配。优化后的骨骼仍须与 UE inspection 对照映射。分区依据 PMX 关节与 mask，不加裙子/外套代理碰撞或避让。

## 动作的两条分支

只有 PMX：物理档案设 `rest_only=true`、`test_animation=""`、`performance_test.enabled=false`，可完成静止 PA/ABP 和静止测试。报告只能为 `rest_measured_movement_pending`。不能宣称走跑、急停、根运动或游戏性能已验证。

有源动画：复制 `templates/animation_export.example.json`，核实 Source/Target mesh、RTG、源动作列表；填 `reviewed=true` 与工作单 `pmx4ue.animation_export_profile`，运行 `animation-export`。输出目录必须空且在本次 namespace 内。工具校验源/目标 Skeleton 和 RTG 配对、时长/数量、输入资产哈希。导出完成不代表视觉通过。新物理版本设 `rest_only=false` 和输出动画路径，不覆盖之前 rest-only 资产。

## 持续移动的物理候选

`simulation` 支持 `space=component/base_bone/world`、`base_bone`、`world_alpha`、`damping_alpha`、四个速度/加速度上限。Base Bone 必须是存在且不参与动态模拟的动画骨。线性单位 cm/s、cm/s²，角速度 rad/s、角加速度 rad/s²。数值依据模型尺寸与动作，不照抄托洛洛。

异步候选设 `timing=deferred` 且显式 `accept_one_frame_latency=true`；保留同参数同步控制。`physics-test` 在实际生成 ABP 上读回节点设置与 PMX shape 过滤；动态版本覆盖 60/30/15Hz、100ms 卡顿及组件移动，20 秒各项。没有周期强制复位。当前包络保护适用于常规人形（半径 500cm），超大模型必须先适配阈值及测试相机，不能直接放宽后宣称通过。

## 性能和验收

启用 `performance_test` 至少三轮、每轮计时至少 20 秒，默认 1920×1080、平均≥70FPS、P99≤16.67ms。每项回读 `t.MaxFPS 200`。采集器用新 PIE 窗口并设置实际 viewport 大小，不把 HighResShot 图片大小冒充跑分尺寸。截图在计时后；记录离屏、动态分辨率/比例设置，viewport 不是内部 shading 分辨率。

必须读取 `performance_review.json`；控制超预算时先分析公共开销，不把候选平均 FPS 高于 60 当作通过。无物理和同步控制同样重复三轮。采集依赖生成的 plan 和新进程数值报告，哈希失配/退出非零/帧率不一致不能验收。单角色 PIE 不等于打包、多角色、LOD 或 CharacterMovement 集成。

## 失败后怎么继续

报告/目录已存在时不覆盖；选择新版本，保留失败日志。厘米 FBX 现已加入有界绑定矩阵精度修正，托洛洛 SDK 和 UE 导入的绑定告警已消除；普通导出保留 `.raw.fbx` 供对照。该步骤不修改层级、骨位置、几何和权重，不接受真实缩放/绑定差异。新角色仍出现 `invalid bind poses` 或 `zero length normal` 时记录为 `executed_with_import_risks`：检查 SDK/导入日志、蒙皮、动作，相关验收不能通过。不得隐藏警告或自动开启时间零重绑来宣布修复。托洛洛仍有零长度法线消息，不能把它当绑定修复已经顺带解决。

mode 2、重复驱动、跨区关节等结构差异按 physics 参考做适配并加测试，不静默忽略。缺贴图/动作可完成其余部分，但保留 pending。重大风格歧义才问用户，能由数据和画面判断的步骤 agent 自主处理。

最终填写 handoff：交付 mesh/Skeleton、材质、IK/RTG、动画、PA/ABP 的确切路径；将执行、绑定、视觉、移动、性能、用户认可分开记录。本机实测范围见 VERIFICATION，不能复制“通过”给新角色。
