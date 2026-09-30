# 验证记录与版本边界

## 截图去重与分阶段清理（2026-09-30）

新截图在产物 PNG 验证、报告落盘与两份 SHA256 一致后，仅删除本轮精确命名的原生临时重复副本；清理失败保留副本并记录。新增 `tools/capture_retention.py`、策略模板与截图保留规程：退役捕获报告/预览运行记录、pin、全项目产物及显式外部引用扫描、只读计划、准确计划批准、工程锁内重检和逐图删除回执。源/目标图、UE 资产、在用图片和历史报告不在清理范围；缺图的旧报告继续被现有验收阻断，不绕过证据检查。

282 项纯 Python 回归通过，其中 12 项新测试使用临时目录合成文件，覆盖原生副本核验、错范围/错哈希/占用、路径链接/非捕获图片拒绝、引用及 pin 保护、运行记录退役、非法豁免、活动锁、准确批准、新增引用阻断、部分失败回执及真实 CLI。没有删除项目已有截图；未运行 UE，新采集器的真实引擎端到端去重仍待验证。修改未提交，旧 ZIP 不包含本轮更新。

## 衣服、脸部与头发统一加宽描边默认值（2026-09-30）

新构建的父材质及通用、脸部、头发实例的宽度系数默认统一为 `0.0012`；保留显式配置优先与脸部跟随通用宽度的规则。同步面部 Overlay 规程，仍按实际 UV 校准嘴角/眼周局部抑制，不自动生成通用遮罩，不修改已有 UE 资产或旧工单。

270 项纯 Python 回归通过，新增两项测试执行实际构建器的宽度表达式，覆盖全部默认值、显式分区覆盖和脸部继承；既有面部校准/分槽挂载测试保持通过。未启动 UE，本次不宣称加宽后的视觉质量或表情稳定性已通过；修改未提交，之前 ZIP 不包含本轮更新。

## PMX 素材目录目标图发现、分区建档与检索（2026-09-30）

新增标准库工具 `tools/target_image_catalog.py`：发现素材目录图片候选、目录提示和可选 manifest 纹理引用，内容去重、稳定 image ID 与原图指纹；agent 实际看图后填写图像用途和丝袜/布料/脸部/全局等区域，query 按标签/特征返回可用原图与 region。支持同源同图的档案刷新，变化或消失的原图不返回为可用目标。同步目标图规程、技能/启动/导入入口、材质设计/审阅、子任务与交接；没有适用图仍正常执行。delivery 既有 sources/comparisons 不改，目录候选不自动变为交付目标。

268 项纯 Python 回归通过，包含 6 项新测试：候选不冒充视觉审核、manifest 引用、同内容别名、分区检索、文件变更/重命名与 PMX 变化、空目录、无审核目标/非法区域框拒绝，以及真实 CLI 输出边界。测试使用合成文件和审核记录，只验证索引行为，不证明识别了任何真实目标图或材质效果。本轮未运行 UE、未修改角色资产、未给真实素材自动填写语义；独立工程使用时仍须由有图像能力的 agent 打开原图建档。修改未提交。

## 按需多智能体协作与能力路由（2026-09-30）

新增 `docs/agent-collaboration.md`、任务书与协作计划模板，接入 AGENTS、技能、启动/导入入口、骨架/材质/物理阶段与交接。能力档为 basic/specialist/advanced，按宿主实际工具、图像能力及已知成本选择，不固定模型名称；确定性操作优先脚本，共享文件和工程操作统一所有权，性能计时避免团队自身重负载干扰。无委派工具或额度不足时继续单智能体处理，审核范围如实记录。

本次实际委派一位较低成本执行者生成两个独立模板，主智能体审阅并统一字段后整合；第二位只读行为演练执行者因宿主额度限制失败，独立演练未完成，不记为审阅通过。技能 quick_validate 已尝试，但当前 Python 缺 PyYAML，未运行到校验阶段；技能 frontmatter 未改，主智能体检查入口、能力档、模板引用和改动格式。此次仅更新规程与模板，没有运行 UE 或验证多智能体角色转换、实际调度成本及效果；运行器本身不增加调度或计费功能。修改保持未提交。

## 面部描边 Overlay 分槽接入（2026-09-29）

预览 outline 新增对象形式：通用/脸/发材质、显式对应槽和排除槽；兼容旧字符串候选。检查槽范围、冲突、材质配对，纳入全部材质的编译与依赖哈希；实际调用原生分槽接口，核对回执材质及应用/排除槽，切换 case 清除上一组。请求配置不冒充逐槽引擎读回。

取消自动启用默认面部 UV 椭圆。显式区域需当前模型校准记录、有效半径和 UV 通道；空区域关闭局部抑制。新增面部 Overlay 说明与嘴角三组 Lit 对照验收，表情/游戏稳定性单列待验。

245 项纯 Python 自动测试通过，包含执行真实预览方法的模拟接口测试、分槽/清除/错误回执和校准配置检查。本轮只更新流程与工具，未启动 UE，未修改角色资产；新版材质构图、原生挂载联测和嘴角实际视觉效果仍待 UE 验证。未提交，先前 ZIP 不包含本轮更新。

## 重点材质效果与游戏交付检查（2026-09-29）

新增 material_review_contract=1，旧 delivery.v2 需补三项 material_features：眼睛层次、头发成束高光、袜边厚度感。审核模型依据、真实槽、专项 A/B、同报告候选两个 Lit 视角和按类观察；无对应表面可有据 N/A，存在但未实现不接受基础贴色覆盖，范围缩减须用户依据。新增 static_lookdev/game_ready 区分，选用描边/边缘光时游戏状态必须单列，game_ready 需遮挡、距离/LOD、运动、光照、多实例、性能六项当前资产报告及原始证据。

性能检查要求同条件关/开、实际开关记录、t.MaxFPS=200、VSync关闭、预热/样本及 Frame P95/P99、Game/GPU P95；按显式预算检查，不用平均 FPS 代替尾部帧耗时。清理材质族和审核模板中强制固定曝光的残留；默认 Open World 场景曝光不变。

本轮只修改工作流、模板、纯 Python 检查器及测试，未启动 UE、未修改角色资产、未提交或打包。235 项自动测试通过；没有宣称 shader 算法、截图或游戏性能在真实角色上通过。具体游戏测试仍由执行 agent 在获准工程中实施，报告真实性与视觉判断不由结构校验代替。

## Face SDF 流程纠错（2026-09-29）

统一内置线性角度烘焙与 Master 的头部平面 atan2 解码；增加非单调受光损失报告/默认阻断，关闭未经 UV 校准的通用鼻唇高光。新纹理审计追踪编码和 manifest 哈希，交付检查要求匹配的 Master 解码读回及至少七个含中间角度的同机位光照采样；分区域观察包括鼻颊、嘴、接缝、过渡、非单调处理。默认 Open World 场景、曝光、截图尺寸政策不变。

227 项自动测试通过，覆盖共享角度公式、实际节点构图函数的数值解释、原烘焙阈值函数、损失检测、编码/证据不匹配和光照采样门槛。UE 5.8.2 中独立角度解码探针编译通过（SM6，零 shader error），仅新建隔离测试材质，没有修改 GPT6Luna 或既有角色资产。首次沙箱运行在 Python 执行前被外部 DDC 写权限挡住；正常权限单次重跑成功。

用户随后要求仅更新工作流，故不继续角色烘焙/UE 实验。新烘焙端到端和解码版本读回尚未做真实引擎联测，完整角色的鼻影形状、连续运动和视觉质量仍待执行 agent 验收；不会因上述编译成功而标为已修好角色。修改未提交、未重新打包。

## 默认日光曝光流程简化（2026-09-28）

单 case 和多 case A/B 都允许 `exposure_ev100: null`，沿用 Open World 场景/工程曝光。移除强制固定 EV100 与独立环境校准前置条件；`environment_review` 变为可选，但显式引用仍检查报告、原图哈希和条件一致，禁止嵌套引用。默认模板只保留原始太阳，不主动增加侧光；SDF 等方向响应测试按需显式添加光照变体。

同步材质、SDF、场景效果与排错指引；自动采集仍不接管用户编辑器，资源不足先协调，不将双开视作必须动作。取景、贴图 mip 驻留、不透明原图与实际看图要求不变。216 项自动测试通过，包含执行真实曝光分支的隔离测试（null 不调用固定曝光设置）。本轮未启动 UE 或重拍角色，不宣称视觉验收；修改未提交，未重新打包。

## UE FK 主链方案（2026-09-28，后续调整）

用户明确目标仅为 UE 重定向，不需要 PMX 控制动画兼容。新增 `goal=clean_ue_fk` 与 `shoulder_strategy=branch_helpers`，新工作单默认采用；现有工作单不静默改写。规划器让肩/上臂及肘/腕绕开 P/C 与 twist，保留辅助骨、权重、附属结构；删除精简仍为显式可选旧路径。中间主链不能以“骨有权重/约束”直接 preserve。review 输出 UE FK 建议，门槛核对真实父级和保留骨，不接受只改 IK 端点。

审计补充 MMD 追加变换与骨骼 Morph；后台打开 blend 时先注册已保存的 mmd_tools 属性，避免把未注册属性误判为没有依赖。报告记录 UE FK 范围，明确不是 PMX 控制动画等价转换。未知补偿和非中性控制需要适配，不能盲目修改绑定。

212项回归通过。实际妮基塔 PMX 经 Blender3.6导入后250骨，8处主骨重挂、0删除；静态最大误差4.14e-7米，8组采样最大5.63e-7米，rest矩阵最大差4.95e-6，厘米/绑定精度合同通过。实际 UE5.8.2 在 `/Game/PMX4UE/NikketaUeFkProbe_20260928/v1` 导入独立网格，读回主链及保留骨后置条件通过，并建立/回读双肩、双臂4条IK链；进程退出0。该IK仅为上肢结构探针，不是完整角色Rig交付。

证据在宿主 `Saved/PMX4UE/NikketaUeFk_20260928/variant_v2/skeleton_apply.json` 与 `ue_structure.json`。没有做完整源动画配对、重定向动作视觉验收、材质或物理实验；不把结构与采样成功等同于全部动作合格。源导入有 `spa` 路径无法作为图片读取的材质警告，未纳入本次骨架修复。修改未提交，上一轮ZIP不包含这次后续调整。

## 肩膀清理与源码测试包（2026-09-28）

修复已直接肩链旁的 P/C 漏判和计划提前退出；允许部分简化链继续清理，并显式检查挂件重挂、权重和引用。计划、Blender apply 和 UE 读回对照应删除骨及最终父链。保留肩部 helper 必须逐骨给出证据；带导入风险的运行记录不能进入下游。支持的 IK/物理写入脚本也检查同一骨骼凭据。旧报告迁移规则见骨骼参考。

托洛洛导出变体已删除左右 ShoulderP/ShoulderC 共4根骨，Blender 骨数664→660；有权重的肩部辅助骨及扭转骨保留。静态最大误差约2.82e-7米，8组肩/肘/腕及组合采样最大约6.03e-7米，厘米导出与绑定精度检查通过。新目录 UE 导入执行了结构后置条件检查；随后实验材质赋值接口报错，已修正测试脚本。此处不以该中间结果宣称角色视觉、重定向动画或物理验收完成。

用户要求停止角色实验、交付工作流测试包；本次仅继续源码检查与打包。包包含当前有效的未提交源码、截图修复和肩膀门槛，不含模型、UE资产、缓存、历史ZIP或本机角色工作单。不会用 Git archive 漏掉未提交/新增工具。便携插件提供源码，需要在测试工程匹配引擎版本重新编译；没有为本次包重新执行独立 BuildPlugin。此前验证章节为历史记录，后续全链与跨模型测试由用户进行。

源码回归208项通过，diff检查通过。新增用例覆盖旧计划缺后置条件拒绝、UE实际残留P/C/错误父级拒绝。使用 `maintenance/package_source.py` 按当前工作树打包，每个文件附 SHA256 清单并回读核验 ZIP 内容；本机角色工作单不分发，历史案例说明保留作参考。

## 主体取景截图修复（2026-09-28）

新增 `FramePreviewSubject`，按实际可见视口投影自动拟合全身/显式部位范围；不再用固定距离与身体中心冒充全身/脸部近景。捕获入口在 Draw 后、ReadPixels 前重验主体可见与投影范围，记录 subject-frame.v1；缺角色、隐藏、错误骨名、裁切、过小目标拒绝落图。视口变化最多重新取景/预热两次。模式切换与取景/捕获均选择可见透视视口。配置和旧证据迁移见 docs/preview-framing.md；v3 不增加像素大小门槛。

201 项自动测试通过，diff 检查通过。宿主 MMD2UEEditor 最终编译成功（4动作，5.93秒，无本次新增弃用警告）。便携桥同步同范围源码，未独立 BuildPlugin。真实 MMD2UE 自有进程直接加载 Open World，以已认可 Tololo 网格取得6张原生1053×592截图（全身/Head近景 × Lit/Unlit/WorldNormal），通过完整 verify_report；逐图15张角色贴图 pending=0，Alpha255。实际打开最终全身/头部 Lit 图：头脚完整留边、近景瞄准脸部，眼睛、发丝和衣料细节可辨。资产依赖与日光地图哈希不变，进程自行退出。

真实负面对照：取景后隐藏临时角色，在捕获时被拒绝，0张图；错误骨名被明确拒绝；用极近机位拍全身被拒绝且未生成PNG。修复前的空景报告也无法通过新门槛。最终证据为宿主 Saved/PMX4UE/CaptureFix_20260928_v1/preview_final_v3.json、negative_hidden.json 和 REVIEW.md；最终编译日志 Saved/Logs/PMX4UE_CaptureFix_VisibleBuild.log。过程中的缺配置、过早检查视口以及视角变化失败均保留，没有覆盖失败文件。最终成功组未触发重取景；重试上限与隐藏不重试另有执行实际 tick 函数的单测覆盖。

此结论仅验证截图链路，不代表重新批准角色材质/骨骼/物理。几何范围不能判断地形/头发遮挡、透明材质、有效但错误的目标选择，仍要求 agent 实际打开原图审核。修改保持未提交，未生成新ZIP。

## 可见截图真实运行与空景负面对照（2026-09-28）

宿主 MMD2UEEditor 已重新编译成功，7个动作、15.81秒。随后在 MMD2UE 自有新编辑器进程中，以已认可托洛洛网格、真实材质编译检查进入现行 ue_material_preview.py；直接加载 Open World，不保存角色或地图。首组取得9张1053×592原生截图，Alpha全部255，逐图15张角色贴图pending=0；实际打开的日光图没有黑屏，衣料细节可辨。全身机位可用，但模板Front裁掉头脚，近景固定瞄准身体中心而非脸部。三个模式的完整矩阵通过verify_report。

另起自有进程只隐藏临时角色组件，生成3张空景负面对照。实际打开首张Lit确认只有天空/地面，但verify_report仍通过且无像素警告。这证明现有检查不能保证截图主体存在、完整入镜或对应所需部位；captured_visual_pending不等于视觉可用。两组角色依赖与日光地图哈希均未变，两个自有编辑器完成后退出。

实测与原图位于宿主 `Saved/PMX4UE/CaptureVerify_20260928/REVIEW.md`、`preview.json`、`negative/preview.json`；构建日志为 `Saved/Logs/PMX4UE_CaptureVerify_Build.log`。这是既有资产的截图实验，不是完整PMX导入验收，也未独立编译分发插件。下方“未编译/待采图”是之前阶段记录；本次未修复取景/主体缺口，未提交或更新ZIP。

## 日光截图 Alpha 与环境审核（2026-09-28）

普通可见视口 PNG 在压缩前显式设 Alpha=255，RGB 不变；便携桥和实验宿主已有 Editor 桥均做同范围源码修正。Python 检查增加完整解码、五种 PNG filter、RGB/RGBA 不透明验证和仅供人工排查的亮度统计。完整但透明/编码异常的图立即失败，保留原图路径，不再等待文件完成。A/B 必须引用已打开审核的固定曝光 Baseline-only 报告，核对图片/报告指纹和相同 mesh、位置、相机、太阳配置及曝光。单 case 日光诊断不需前置审核，不增加尺寸门槛。

`tests/run_tests.py`：195 项通过；diff 检查通过。只读复测 DeepSeekTest v6 的首张原图：1053×592，共623376像素 Alpha=0，正确拒绝。既有 review_opaque 副本 Alpha=255、RGB均值约[162.91,157.67,157.34]，像素合同通过；它只是诊断副本，不是修复后原生采图证据。未修改该工程。

检测到两个 UnrealEditor 和一个 dotnet 进程，当前权限不能读取它们的命令行，因此本轮未启动构建、关闭任何进程或取得新截图。C++ 编译及新进程采图仍待验证，不宣称已修复目标工程实际运行画面。修改未提交、未更新 ZIP。

随后对骨骼流程的只读审核发现现有上肢门槛仍不充分，见 `docs/audits/2026-09-28-skeleton-stage-gates.md`。195 项通过不覆盖这些新发现，不能当作骨骼完整验收证明。

## 上肢审阅、场景效果与 Rotator 修复（2026-09-28）

根因：工作单默认 preserve，旧运行器只有选择 upper-only 时检查 skeleton_reviewed，IK/物理入口没有上肢决策检查。已有 planner 支持双臂扭转骨转旁支、肩辅助骨安全清理，不是没有算法。现在增加 skeleton-review 阶段和骨骼决策模板；执行时审阅手臂/肩膀，核对源身份、优化计划/FBX/导入记录以及 IK/物理目标网格。合理链允许保留，未审阅不允许默认跳过；不新增腿骨清理或重复腿骨验证。纯材质复用阶段不触发重导出。

只读核对 TestCharacter 的 Nikketa original_v1_daylight_v9：outline 配置 enabled，depth_rim disabled，material_preview_openworld_v9 的 cases 只有 Baseline。这证实配置启用不等于预览挂载，不能凭配置宣称描边已经生效。现新增 scene-effects-build（只生成显式选择的候选，不改关卡）、预览挂载回执和 delivery.scene_effects 必填决策；需要 stencil 时只在自有预览进程临时启用并回读，不写项目配置。按模型不采用效果需有依据，不能把用户要求自动改成可选省略。

便携 tools 全部 Rotator 调用改为命名参数或无参 identity；日光模板方向、侧光 yaw_offset 与旧自定义灯光表达式分别通过 roll-first 模拟绑定测试。逐图实际太阳旋转增加回读核对。没有改动原工程历史案例脚本或 TestCharacter 文件。

`tests/run_tests.py`：186 项通过，包括审阅缺失阻止 IK 启动、原始/优化 FBX 证据及错误目标网格拒绝、只有材质没有挂载不能通过、显式场景效果构建/拒绝覆盖、全部 Rotator 位置调用扫描和实际旋转表达式测试。Python 语法检查与 diff 检查通过。场景构建调用采用 mock 验证调度；本轮未启动 UE、编译原生桥或取得新截图，因此新增 UE 构建、stencil 临时设置和真实日光画面仍待实测。所有修改保持未提交，未更新旧 ZIP；下方章节是此前阶段记录。

## 脸部 SDF 收尾与交付 v2（2026-09-28）

针对独立工程将脸部 SDF 留为“后续若需”的记录，新增 `docs/face-shading-workflow.md`，将执行时点固定为首组可用基线后、静态材质交付前；SDF 贴图生成与 `face-sdf` 运行时驱动入口明确分开。交付 v2 必须声明 `face_shading`，未完成、占位绑定、关闭的通用图开关、缺正面/左右光照证据均不能作为静态脸部已完成。允许有证据的替代算法；无动画只影响运行时。旧 v1 须补决策/证据再审核。

新增 Blender 只读图片数据检查，验证本工具 R 阈值/A 覆盖约定，拒绝有效覆盖内恒定的阈值；不要求 alpha 必须含黑色，也不要求未使用的高光 G/B 有变化。对 TestCharacter 的 v9 `T_PMX4UE_Neutral_face_sdf.png` 实际运行：4×4，RGBA min=max=1，结果 invalid、Blender 退出码 1，符合预期；源项目未改。报告在宿主实验项目 `Saved/PMX4UE/WorkflowSdfClosure_20260928/neutral_audit.json`，该路径是验证记录，不是移植依赖。

`tests/run_tests.py` 175 项通过，含完整交付正例及关闭 SDF 后失败、占位/覆盖外变化拒绝、贴图源变更与错误审计源、替代算法、无动画静态完成和旧清单迁移。Python 语法检查、diff 检查通过。UE 验证器增加实际标量及 SDF 导入源哈希读回，已核对本地 API 定义但本轮未在 UE 执行；未烘焙新角色 SDF，也未宣称其材质视觉完成。没有修改原角色资产或提交 Git。

## v3 日光地图与贴图加载修正（2026-09-28，待 UE 验证）

根据独立工程的反馈，移除材质预览的视口最小宽高要求；尺寸只记录为截图元数据，不作为清晰度验收条件。v3 配置不再接收 `level`：自有可见编辑器直接加载安装目录的 `/Engine/Maps/Templates/OpenWorld`，临时角色与材质覆盖只在内存中存在，绝不保存引擎地图；报告校验地图源文件哈希未变。截图前逐项检查角色当前材质实际使用的 `/Game` Texture2D 的 mip 驻留；60 秒仍未就绪则失败并报告路径与 mip 数，不以改变视口大小或 `r.ScreenPercentage` 掩盖贴图未加载。实际模糊原因仍需人工用原尺寸图片与材质输入核实，此检查只是消除已知的未驻留风险。

`tests/run_tests.py` 本轮 163 项纯逻辑测试通过，包括 v3 不接受自定义地图/尺寸门槛、1×1 可见 PNG 在贴图就绪时可通过合同、物理性能阶段仍可离屏。未编译新增 UE 原生接口、启动 UE 或取得截图；日光地图加载、纹理驻留接口和真实材质画面仍待目标工程验证。下方 v2/v3 旧章节是当时的历史记录，不代表当前 v3 约束。

## 材质预览测试断言修正（2026-09-28）

`tests/test_workbench.py` 曾要求 `material-preview` 启动参数包含 `-RenderOffscreen`，与 v3 可见视口采集及离屏图不得作为材质视觉证据的契约相冲突。现改为明确禁止该参数，并单独检查物理性能阶段仍保留原有离屏启动；仅修正过期测试，不放宽截图来源门槛，也不修改实际启动逻辑。此前测试包不含本修正，应重新打包后交给其它工程验证。

修正后运行 `tests/run_tests.py`：163 项纯逻辑测试通过；未启动 UE、Blender 或进行截图视觉验收。

## 可见视口材质采集 v3（2026-09-28，待引擎验证）

针对另一工程离线截图模糊，材质预览启动参数移除 `-RenderOffscreen`；新增可见编辑器视口 backbuffer 读取接口，v3 配置以实测视口像素而非请求输出尺寸设门槛，并记录截图来源和 `r.ScreenPercentage` 设置。旧 v1/v2 报告不能通过新版视觉证据闸门。保留全身/近景原尺寸人工审查和模糊定位要求，脚本不自动宣称图像清晰。

本轮 `tests.test_material_preview_contract` 16 项通过，Python 语法检查与 `git diff --check` 无错误。尚未编译 UE 原生桥、启动编辑器或取得 v3 截图；运行时 API 和实际清晰度须在目标工程另行验证。未修改 TestCharacter 或妮基塔资产，未提交、未打包；下列章节是各历史轮次的记录。

## Open World 日光预览基线（2026-09-28，待引擎验证）

预览示例升级为 v2，从真实 `/Engine/Maps/Templates/OpenWorld` 复制新隔离地图，复用模板太阳/天空光，检查天空与地形已加载，记录环境与逐图太阳参数。首次基线保留模板/工程曝光；材质多 case 对照要求先校准固定 EV100。旧 v1 保留原单灯复现语义并警告，不能冒充日光基线。已接入材质技能参考、流程和视觉审核模板。

只读核对本机 UE 5.8 的 BaseEngine.ini 模板路径、LevelEditorSubsystem::NewLevelFromTemplate 的 LoadAsTemplate/保存实现及 SkyLight Recapture 接口；这不是运行验证。按用户测试交接约定，本轮未运行测试、UE、Blender、编译或截图，新增合同用例未执行。World Partition 区域加载、外部 Actor 保存/重载、实际曝光/成图和跨版本 API 仍需目标工程测试；缺环境报错，不自动回退暗场景。没有自动亮度判定器，不宣称已改善实际截图。未改原工程 Content、未提交或更新 ZIP，旧包不含这些变化。

## 材质算法与实际资产的适用性检查（未执行实验）

针对“从丝袜参考观感直接推断透射”的反馈，补充资产优先的材质决策规则、事实/假设/验证记录和丝袜分支示例；接入技能入口、材质参考、设计/视觉审核及导入任务模板。目标图仍可选，不将所有丝袜固定成透明或不透明，也不增加自动改 mesh 的行为。

仅修改流程文档与模板，静态差异复核；未运行测试、UE、Blender 或视觉实验。未新增几何层自动检测器，现有 delivery-check 不能自动判断材质算法与 mesh 是否相符，仍需 agent 读取实际资产并看图。未提交或更新压缩包；此前移植包不含本节新增指引。

## 可选目标图环节（2026-09-28，归档后修改）

按用户澄清，将目标图分析与结果对照作为可选环节接入技能与模板：有图时分析外观并辅助材质迭代，无图按 PMX、纹理及文字要求继续，不阻塞导入或降低已有视觉检查要求。撤除上一轮误解产生的强制目标编号和额外审批表述。

本轮仅修改指引和模板，未运行测试、UE 或视觉实验，未修改交付检查器；目标图仍由 agent 实际看图分析。此次改动未自动提交或重打包，先前 `9e54d18` 源码 ZIP 不包含本节修正。

## 工作流更新源码归档（2026-09-28）

按用户要求提交本轮环境兼容规程、FBX 类型适配、材质族路由、隔离预览、材质迭代和交付证据检查，并从该 Git 提交导出源码 ZIP。压缩包文件名包含日期与提交短哈希；以此定位本次更新，不将旧 0.2.0 归档与本次更新包混用。

本次只检查 Git 差异与归档文件清单，不运行测试、UE、Blender 或编译；验证由用户后续在另一 agent 中完成。下方“未提交”描述是各实现阶段的历史状态，不再代表本次归档状态；“未验证”边界仍然有效。包内不含预编译插件、角色源资源、缓存或 Git 历史。

## 工作记录审阅后的材质迭代补强（2026-09-28，未执行测试）

只读参考 TestProject 工作记录后，在工作台内新增：逐槽显式纹理/中性输入及完整路径读回、通用 Master 缺输入依赖归零与 material_debt、同纹理跨采样类型冲突检查；material-preflight 小型采样器/连接/编译探测；material-build 复用已保存 mesh/纹理并生成组件覆盖清单，不改旧网格；delivery-check 检查显式资产组合、上游风险、有效输入、槽覆盖和同条件 A/B 证据。对应操作接入材质技能参考、任务与交接模板。

兼容边界：旧配置若依赖其它槽的默认纹理，外观会改变并可能出现待处理效果；声明未支持的纹理角色现在明确报错，需要图及绑定适配，不能据此声称 sphere map/opacity mask 已实现。自定义父图的艺术输入依赖仍由 agent 适配。预检只覆盖小图，交付检查不替代实际看图、引擎兼容或物理/性能验收。

本轮未启动 UE/Blender、未编译、未截图、未运行测试或 Python 语法检查；新增纯逻辑回归用例待另一个 agent 执行。只做源码和差异复核，未修改 TestProject、原工程 Content 或已认可资产，未提交、未重建分发包。历史测试通过数不包含这些修改。

## 角色材质族与显式父路由（2026-09-28，待验证）

用户要求材质质量不能止于颜色正确。只读核对 Cecilia 独立丝袜父图历史报告、托洛洛配置和工作台实际源码，并结合用户提供的旅人渲染笔记文本，新增材质族设计说明、设计模板、工具能力/差距表和局部验收要求。未获得文章中图片文件，未作该参考图的视觉匹配。

实现：`parent_assets` 保留到规范化配置并验证；未知/冲突父路由不再回退 Master。stocking/cloth 专用构建器新增 graph-only 和显式槽选择，由 ue-build 在实例创建前调用；缺关键输入停止而非跳过。专用/自定义图检查声明参数是否实际存在，实例与验证报告记录/核对父路径；普通通用图旧路线保留。新路由要求明确 Normal/RMO，避免其它槽纹理作为实际表面细节。预览关键灯标记为 atmosphere sun 0，以对应现有风格化图的光向输入。

未生成新的 UE 材质、未编译/运行 UE、未运行测试；只做源码与差异复核，新增回归用例待另一个 agent 执行。没有实现任意模型自动四层眼睛、严格 clip-space 描边或文章同款多 Pass；这些能力与近似的差距已明确交接。旧手动改父但未更新 material_map 的工作单会在新验证器报不一致，需在独立新版本同步路由。原工程已认可材质与 TestProject 均未改动，未提交。

## 独立工程反馈后的流程补强（2026-09-28，未执行验证）

- 新增 `material-preview` runner、受启动标记保护的独立编辑器/隔离预览地图、组件级材质/标量覆盖与可选 outline/depth-rim 对照、同视角/光照/模式采集、异步 PNG 完成/尺寸/CRC/指纹检查。只保存基线地图，不保存原网格/材质；旧 current-level 类型清理与 preview/full 入口禁用。
- 新增材质审核文档/模板、未分类纹理处置、用户要求与可选风格的区分；源码包含截图入口不代表聊天会话必须有对应工具。采集终态仅为 `captured_visual_pending`，实际视觉仍由 agent 看图。
- Blender FBX 类型编码改为读取当前 codec 合同，保留完整回读。只读核对本机 3.6/5.2 类型定义；未重新导出。材质连接错误补充实际 pin/引擎诊断，空采样器默认纹理及关键属性失败改为明确报错；未改主材质计算公式。
- 独立 TestProject 仅供只读参考，按用户要求不移植其未充分验证的非对称角限和材质实验实现；PMX 非对称关节仍是明确缺口。之前的 UBT Trace 沙箱处理规程保留。
- 本轮按用户此前测试交接要求，**没有运行测试套件、Blender、UE、编译或截图采集**。新增纯逻辑测试只是待运行用例，不是通过证据。原有 127 项等历史通过数不包含本轮变更。新预览路径需在目标工程实测 API、实际成图、隔离/不覆盖、超时和 A/B 重置；不能据此声称材质视觉已经验收。
- 只修改 PMX4UE 工作台，未提交、未重建旧源码 ZIP，也未修改原工程 Content 或参考工程文件。迁移时旧 ZIP 不包含这些工作树改动。

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
