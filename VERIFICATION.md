# 验证记录与版本边界

## 0.2.0 源码归档（2026-09-27）

按用户要求归档此前有效但未提交的通用补全、物理迭代、测试及案例证据，并加入独立迁移入口 `START_HERE.md` / `templates/import-agent.md`。本节之后的“未提交”“未运行”等文字保留历史时间点，不作为当前 Git 状态；各阶段的实测限制仍然有效。

本版包含完整的通用脚本与插件源码依赖，不包含历史资产、缓存或预编译插件。源码版本为 0.2.0；旧 `.local/PackagedPlugin*` 不含最新 SDF，不能作为本版二进制分发。本轮不新建 UE 工程，不把源码归档宣称为新角色全链或打包游戏验收。先前独立编译记录仅覆盖各自当时源码；含最新 SDF 的完整插件应在目标引擎重新构建。

最新 SDF 验证见 `characters/TololoSchool1001/face-sdf-runtime-v1-decision.md`：实际材质编译、新进程重载及 120 帧动画参数测试通过。本轮在用户要求停止测试之前已运行工作树 127 项 Python 测试，通过；随后按要求不再执行解压副本测试、UE 编译或功能验证，交由另一个 agent 在目标工程测试。新增发行结构检查不等于源码包已实际跨工程运行。FBX 精度修正依赖 Blender/FBX 的实际实验，不由纯 Python 套件代替。上半身导出分支、跨模型视觉、LOD/打包、多角色及完整性能验收仍保留待验证项。

日期：2026-09-26。此文件区分原工程经验与**复制后的独立工作流**实测。

## 通用流水线补全（2026-09-27，未提交）

以下是本轮最新证据，优先于下方历史的“未运行/旧采集器”描述。测试均在 MMD2UE 新命名空间，不覆盖已认可资产；独立插件仅做分发构建，不重复安装到 MMD2UE。

- 新增能力探测与 MMD2UE/PMX4UE 双 provider 适配、PMX 原始骨名映射、审核式动画批导出、rest-only 分支、Base Bone Space/运动限幅、通用 15/30/60Hz 与卡顿/持续移动测试、实际尺寸 PIE 性能采集及复核、材质编译阶段。
- 114 项离线回归、Python compileall、diff 空白检查通过；独立插件 Editor、Game Development、Game Shipping BuildPlugin 退出 0；MMD2UEEditor 最小桥编译通过。
- 动画批导出：真实 UEFN→托洛洛新动画保存，输入哈希不变。输出 `/Game/PMX4UE/WorkflowProbe/v1/Animations`。加强 Skeleton/Rig 哈希保护后，再用通用合同生成的 RTG 导出 `/Game/PMX4UE/WorkflowPoseProbe/v1/Animations`，退出0；报告在该配对的 `animation_export.json`。源动作 PoseSearch Notify 有序列化警告，动画通知语义仍须审核，不将位姿导出成功视为玩法通知完整验收。
- 通用 Agent T-Pose 合同：实际不同 Source/Target 的采集→模型/配对→编译→写入→新进程重载通过。位置误差 0，旋转最大 <0.000003°；新资产 `/Game/PMX4UE/WorkflowPoseProbe/v1/RTG_AgentContract`。视觉/更多动作仍单独待验收。
- 通用动态物理：2 PA + 4 ABP 构建成功，新进程 4 项基础和 6 项运动/卡顿测试完成，444 动态骨骼及 shape 过滤读回通过。使用审核过的案例分区，不是任意模型自动语义识别；也没有把最新 ChestFollow 外观决定强行设成通用默认。
- 无动画分支：独立 `/Game/PMX4UE/WorkflowRestProbe/v1/Physics` 的 PA/静止 ABP 构建及新进程 720 帧测试通过，结果 `rest_measured_movement_pending`；没有动画或性能伪通过。报告 `Saved/PMX4UE/WorkflowRestProbe_v1`。
- 真实 PIE 三轮交替：实际 viewport 1920×1080、离屏、t.MaxFPS=200、20 秒计时/项、进程退出 0。候选平均 76.34–78.65FPS，最差 P99 18.60ms；无物理平均 70.91–77.69FPS，最差 P99 19.25ms。复核为 `control_below_budget`，不是稳定60FPS通过。视口尺寸不是内部 shading 分辨率；HighResShot 1000×1000 图片只是计时外画面证据。
- 材质父链编译：现有角色三个 master 在 PCD3D_SM6 编译成功、退出0，不保存材质；不是从新 PMX 全套新材质的视觉验收。第一次拿历史不同 schema 报告被阻止，保留失败日志。
- Blender 源身份：注册 mmd_tools 后读取实际 .blend，616 个唯一原始 PMX 名→导出名，无歧义。初次未加载插件得到空映射并失败，未猜测补齐。

本机报告：`Saved/PMX4UE/WorkflowProbe_v1/`（animation_export/physics_build/physics_test/material_compile_v2/bone_identity_v2）、其 `Performance_1080p_v2/performance.json` 与 `review.json`；姿态 `Saved/PMX4UE/WorkflowPoseProbe_v1/`。源码复现入口在 maintenance，包含案例路径，不能作为通用默认配置。新项目按 `docs/fresh-project-runbook.md` 重新初始化。

**绑定告警修复（同轮后续）：** 原始厘米 FBX 在 SDK 有83个相对矩阵不一致，重算 Cluster.Transform 无效。查明近单位基底存在累计尺度漂移，加入 ≤100ppm 的有界正交化与双精度相对矩阵重算，完整绑定姿态 SDK 检查通过；UE 新目录 `/Game/PMX4UE/WorkflowBindProbe/v2` 导入退出0，无 invalid bind poses、无非单位组件骨。最大绑定基底元素调整约 0.00003743，平移、模型局部变换、层级、顶点/权重/形态键均未改；编码后逐字段重读校验。`tools/blender_fbx_bind.py` 已接入普通厘米和 upper-only 导出，普通导出保留 raw。再次从原 PMX 运行新的普通导出成功（664骨、源名映射、单位检查）；上半身分支接线仍未单独重跑。本轮未做修正后整套动态蒙皮视觉验收。

SDK 中原有单 mesh 的不完整 shape bind pose 仍报告缺 deformer，但完整 skin bind pose 通过，UE 不再输出绑定警告。不随意删除 shape 数据。旧审计误把相对 Transform 当全局矩阵，已更正。**零长度法线消息仍在**，不属于此精度修正范围。新模型任何绑定/法线风险都会记录为 `executed_with_import_risks`，不自动生产通过。证据：`Saved/PMX4UE/WorkflowBindProbe_v2_import.log`、`WorkflowBindProbe_v2/inspection.json`、`WorkflowExportProbe_v3/blender_manifest.json`。

本机出现 Zen 缓存 Insufficient Storage (507)；未更改缓存/RHI/画质或删除用户数据，也不凭共现认定其导致性能尾帧。第二角色、新项目全链、打包/多角色/接触质量仍待各自实测。不能把本次工具补全称为任意 PMX 全自动生产验收。

## 物理流程再整理（2026-09-27）

新增 `docs/agent-physics-workflow.md`、`templates/physics-agent.md` 和离线 `tools/review_physics_benchmark.py`，连接技能参考、README 与交接模板。流程包括换动画不绕过 ABP 物理、按症状选择最小实验、实际 GameViewport 证据及分层验收。本轮只改工作台工具/文档，不改 UE 资产，不重新启动 UE，不自动提交。

- 纯逻辑回归 101 项通过（新增 10 项，覆盖缺失证据、帧数不一致、非有限值、非零退出、P99 超预算、控制异常、重复不足、小视口和输出拒绝覆盖）。
- 复核真实 `Saved/PMX4UE/PhysicsAcceptance_Offscreen_v3/report.json`：`measured_scope_pass`，实际 655×325，`viewport_target_met=false`，`production_accepted=false`。输出位于同目录 `review-workflow-v1.json`；默认 1080p 目标不满足时 CLI 返回 2，这是范围不足，不是物理失败。
- 真实 UE 测试沿用 [物理复测记录](characters/TololoSchool1001/physics-acceptance-v2-decision.md)，不是本轮重新跑分。用户随后认可物理观感；这不能替代完整接触、目标分辨率、打包和多角色验收。
- 新工具仅处理已知 `tests[]` 报告格式，复核的是记录的过程与数值；进程退出码由启动器/agent 提供，完整依赖哈希与画面仍由 agent 核查。不是通用 UE 采集器或任意 PMX 的自动生产批准工具。

## Agent 通用 T-Pose 流程（2026-09-27）

新增双侧原生采集入口、可复用模型档案、绑定采集指纹的配对方案、离线 draft/plan、执行前重编译校验、新进程重载入口和无上下文 agent 指引。腰/骨盆等 `pre_edits` 在四肢求解之前执行，保留旧手写 profile 与后置微调兼容。

91 项离线回归通过（原有 78 项 + 新增 13 项），新增用例覆盖异名/不同体型/不同组件方向、Spine 误含腿祖先、映射错误、失效指纹、Scale=100、修正顺序、CLI 产物、防覆盖，以及模拟 UE 接口下写入前拦截和重载审核状态。接口模拟不是 UE 集成测试。只读核对本机 UE 5.8 控制器声明；未启动 UE、未编译引擎模块、未生成新 uasset，未做第二个真实角色的视觉/动态验收。已有用户认可案例保持不动。详细操作和边界见 `docs/agent-retarget-workflow.md`。

## 本轮提交与用户验收（2026-09-27）

用户在查看 v5 后反馈“效果很好”，并要求提交这些尝试。将 v5 记为本模型当前用户认可的重定向基线；自动验证仍限于姿态、链配置、持久化及原资产不变，不扩展为所有动画均已验收。历史小节的“未提交/待验收”描述保留其当时状态，由本条补充最终交接结果。PMX4UE 提交工具、测试和决策记录；MMD2UE 单独提交最小编辑器接口、IK 模块依赖与 TPose_v1–v5 测试资产。源模型、源动画、材质及旧物理修改不在本次范围，不构成独立可迁移的完整角色包。

## Spine v5 链语义对照（2026-09-27）

在 MMD2UE 复制独立 v5 Target Rig 和 RTG，仅将目标 Spine 起点 Groove 改为 UpperBody，结束仍为 UpperBody2。Center 骨盆、腿链、Source Rig、双侧 v4 命名姿态、链映射、Op 顺序/开关保持；同步各 Op 的 Target Rig 引用。原 mesh/Skeleton/Rig/v4 RTG 文件哈希未变。生成和新进程重载均成功，姿态最大位置差 0 cm，旋转差 < 0.000004°；78 项现有回归测试通过。未播放验证动态效果，不宣称已解决行走偏移；根运动旧配置及其警告留待单独排查。报告：`Saved/PMX4UE/RetargetTPose_v5/spine.json` 和 `reload.json`。

## T Pose v4 站姿匹配（2026-09-27，未提交）

v3 仍存在 Source 外张/Target 收拢的中立姿态差异。新增审核方向驱动的腿段匹配，固定髋宽/骨长并保持脚掌组件旋转。原生读回 Source 踝间距 30.52171 → 12.49731 cm，Target 保持 10.92118 cm；两侧腿段方向误差 < 0.000001°，上身位置差 0 cm，脚掌旋转误差 0°。Source 脚踝下降约 0.324 cm。78 项测试通过。新资产 `Rigs/TPose_v4/RTG_UEFN_To_Tololo_TPose_v4`，详见 `characters/TololoSchool1001/tpose-v4-decision.md`。尚未确认鞋面贴合、蒙皮穿插或动态动画效果。

## T Pose v3 下肢修正（2026-09-27，未提交）

用户认可 v2 上半身，但下肢不合格。v2 仅审核腰颈连线不足以代表全身：共用父骨恢复后，D 腿/膝遗留约 41.53° / 2.13° 偏移导致腿部倾斜。v3 只恢复这四处 Retarget Pose 偏移，不改 mesh 或骨架；新资产在 `Rigs/TPose_v3/RTG_UEFN_To_Tololo_TPose_v3`。UE 原生髋踝倾斜约 44.685° → 3.51348°；上半身及其它不受影响骨骼位置差 0 cm。Source 未变。76 项纯逻辑测试通过；本轮仍需用户侧视和动画复核。详见 `characters/TololoSchool1001/tpose-v3-decision.md`。

## MMD2UE T Pose v2 躯干修正（2026-09-27，未提交）

- 用户确认 v1 呈 T 但目标后仰。定位为当前姿态继承的 Center / Groove / Waist / UpperBody 旋转偏移，不是 mesh 变更。
- 通用工具支持显式恢复参考旋转，再计算手臂，并对审核的关节连线倾斜做写入前及 UE 原生读回检查。新增回归用例，75 项测试通过。
- 新资产：`/Game/Characters/TololoSchool1001/Rigs/TPose_v2/RTG_UEFN_To_Tololo_TPose_v2`；两侧当前姿态为 `TPose_Source_v2` / `TPose_Target_v2`。
- UE 原生目标腰颈连线倾斜 13.965632° → 0.570628°；Source 保留原有约 4.193159° 骨盆到颈连线倾斜，不强制两种体型具有相同曲线。双侧臂段最大方向误差 < 0.000003°。
- 生成与独立新进程重载均退出 0。重载位置与保存时完全一致；原 mesh、Skeleton、Rig 和 v1 RTG 哈希保持不变，链映射及操作开关不变。
- 按骨骼处理指引，本轮只更改命名重定向姿态。未生成新动画；视觉和动画审核仍待进行，保留既有根运动相关配置，不将静态数值验证称为全身动画验收。
- 报告：主工程 `Saved/PMX4UE/RetargetTPose_v2/normalize.json`、`reload.json`。复现入口 `tools/ue_mmd2ue_tpose_v2.py`，决策记录 `characters/TololoSchool1001/tpose-v2-decision.md`。

## MMD2UE 内双侧姿态规范化（2026-09-27，未提交）

按用户要求撤回 `3d7b3e2` 并保留所有修改，PMX4UE HEAD 回到 `9fc9756`。后续实验默认使用 MMD2UE，不另建 UE 工程；此后的规则优先于下方历史空白工程记录。

- 在 MMD2UEEditor 新增最小 `MMD2UERetargetTools` 读取接口，Development 编译通过，未安装整套 PMX4UE 插件。
- 从原 `PhysicsSandbox/IK_Tololo_Mann` 创建新版本。Source 为真实 `SKM_UEFN_Mannequin`，Target 为用户认可的 `SK_TololoSchool1001_UpperOnlyCm_v1`。
- 原目标 Rig 只有 Spine / LeftLeg / RightLeg。复制 Source 与 Target Rig，补齐 LeftArm / RightArm / LeftClavicle / RightClavicle / Neck / Head，形成 9 条已映射目标链。保留原脊柱/腿部映射与操作开关。
- 生成 Source 的 `TPose_Source_v1` 与 Target 的 `TPose_Target_v1` 并设为当前姿态。只自动规范双臂方向，没有改 mesh、绑定姿态或腿骨。
- 验收捕获到 UE `SetIKRig(Target)` 不同步 Op 自定义 Rig 引用的问题。使用 `assign_ik_rig_to_all_ops` 修复本轮新资产，并补入生成脚本。FK Chains / Run IK Rig 的内部引用均已验证；没有重建整个 Op Stack。
- MMD2UE 新进程重载通过，双侧命名姿态、9 条映射和 Op Rig 引用持久化正确；原重定向器、原 Source/Target Rig 与 mesh 文件哈希保持不变。73 项纯逻辑测试、技能结构校验通过。

在 MMD2UE 内容浏览器打开：`/Game/Characters/TololoSchool1001/Rigs/TPose_v1/RTG_UEFN_To_Tololo_TPose_v1`。`Basis` 是保留原姿态的链条设置对照，不是最终 T-Pose 版本。

报告位于主工程 `Saved/PMX4UE/RetargetTPose/normalize.json`、`reload.json`；生成脚本为 `tools/ue_mmd2ue_normalize_tpose.py`，已有输出拒绝覆盖。本轮未导出新的动画或做动画视觉验收，手掌轴向扭转仍未自动匹配。所有修改保持未提交。

## T-Pose 编辑增量验证（2026-09-26）

- 新增 `retarget-pose` 阶段、双臂几何对齐、逐骨局部轴角/四元数偏移编辑；写入独立重定向器的原生命名 Retarget Pose。
- 73 项逻辑测试通过；新插件 Editor / Game Development / Game Shipping 编译通过；独立空白项目 API probe 通过。
- `.local/TPoseProbe_v1` 使用托洛洛原始厘米骨架（包含 ArmTwist / HandTwist 中间骨骼）完成真实 UE Source+Target 双侧自动对齐、Target 手腕 +5° 微调、Source 手腕 -5° 单独编辑。
- 双臂初始偏差约 35.05°，原生解析后的最大方向误差约 0.00000242°；预测与 UE 的最大位置误差约 0.00000326 cm。
- 新进程重载自动/手动姿态后，位置与保存前一致；原重定向器保持原状，非编辑骨骼的局部偏移保持原状。
- mesh 与 Skeleton 文件 SHA-256 与测试输入副本完全一致，没有改绑定姿态或重写 mesh。
- `pmx4ue.py run --stage retarget-pose --execute` 实际执行成功、退出 0，生成独立资产及阶段记录；已有输出拒绝覆盖。
- 测试资产：`/Game/PMX4UE/TololoProbe/v1/PoseTest/RTG_TPose`；手动版本为 `RTG_TPose_Manual`、`RTG_TPose_SourceManual`。仅在独立测试工程，不在原 MMD2UE 项目。

边界：本轮 Source/Target 使用同一测试 Rig 验证编辑接口，不代表 Manny→托洛洛等跨角色动画视觉验收。未做完整材质画面、掌心扭转匹配或全身 T-Pose 自动化。已有 bind pose 导入告警也不由此功能修复。

初次测试因 Content 复制多嵌套一层而未找到 Rig，修正独立测试目录层级后重试通过；保留了失败日志，不修改原测试输入资产。使用方式见 [T-Pose 编辑说明](docs/retarget-pose.md)。

## 本轮独立验证

环境：Windows 11，Blender 3.6.23，UE 5.8.2 (`56702186`)，MSVC 14.44 / Windows SDK 10.0.22621.0。

| 检查 | 结果 | 边界 |
|---|---|---|
| `python tests/run_tests.py` | 64 项通过 | 纯逻辑/运行器，不代表画面合格 |
| Python compileall | 通过 | 仅语法 |
| skill-creator quick_validate | 通过 | 技能入口结构，不代表 agent 行为已完成跨模型验证 |
| 独立 RunUAT BuildPlugin | Editor、Game Development、Game Shipping 均通过，退出 0 | 编译，不是打包游戏帧率 |
| 空白项目插件加载/API probe | 通过，退出 0 | 无原 MMD2UE 模块或内容依赖 |
| 托洛洛原 PMX → 独立 Blender/FBX | 通过，退出 0 | 未修改源 PMX；不携带模型到仓库 |
| FBX 单位契约 | 单位系数约 1；mesh/armature scale 1；Center 位移 84 cm | 局部样本与 root 检查，不代替 bind/动画 |
| 新目录 PMX physics inventory | 通过 | 只读取物理数据，未在新工程重做动态物理 |
| 材质未审核草稿、骨骼审计、配置草稿 | 生成成功 | 草稿未假装审核完成 |
| 空白工程 FBX 导入 + C++ 骨架检查 | 导入成功，组件空间非单位缩放骨骼为 0 | **有绑定姿态警告，见下方** |
| 配置驱动目标 IK Rig | 7 条链 + Center pelvis 创建、保存通过，退出 0 | 未导出动画；未宣称重定向视觉通过 |
| 原工具来源哈希复核 | 复制来源无变化 | 本轮未改写原工程工具 |

实际测试生成物留在本机 `.local/BlankProbe_v2/`，不提交，也不是便携工作流的运行依赖。空白工程只使用 PMX4UE 插件；导入只写 `/Game/PMX4UE/TololoProbe/v1/`。

本轮发现并修复：Blender 导出脚本的旧包路径、物理盘点对托洛洛脚本的数学函数依赖、材质预设绝对定位、基准测试的专用资产 fallback、UE `SkeletalMesh.get_all_bone_names` 不存在（改用插件只读检查接口）、UE object path 与 package path 比较差异。

## 没有解决/没有重新验收的内容

1. 空白工程 Interchange 导入日志仍有 `Imported skeleton has some invalid bind poses`，引擎使用时间零姿态重绑；另有 MikkTSpace `zero length normal` 消息。**导出基线尚不能标为生产级绑定姿态验收通过。** 已附 `blender_audit_fbx_bind_pose.py` 供 agent 后续分析，不能通过隐藏警告冒充修复。
2. 新包装未在全新项目重新验收完整材质外观、上半身修改后的所有动作、重定向导出、裙子/外套/头发模拟及 PIE/打包性能。旧项目的成功效果不能自动转移为此版本的全链通过。
3. 物理底层来自已有 native RigidBody 方案，碰撞/关节/参数计划有回归测试；PMX mode 2 等特殊语义仍需适配。不是任意 PMX 的完全等价 Bullet 复刻。
4. 未进行独立无上下文 agent 的真实跨模型全链测试。本轮提供了完整交接入口、脚本和报告机制，但不把它称为已经验证的任意角色一键转换。
5. 原性能案例曾在报告生成后发生编辑器退出崩溃；运行器保留非零退出失败判断，未在本轮证明关闭问题已修复。

## 下一次最有价值的验证

由新 agent 使用一个新角色 PMX 和空白工程，根据 README 建立工作单，逐项记录 material / bind pose / retarget / physics / performance 结果；只为真实遇到的差异修改脚本。绑定姿态问题优先定位；不能跳过后直接宣称整套流程可投入游戏。
