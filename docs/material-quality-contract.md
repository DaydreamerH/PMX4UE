# 重点材质效果与游戏验收

## 三类效果不能被“颜色正确”替代

有对应表面就要分析和实现，无目标图也照做；源数据不支持某算法时适配实现，不强行加几何或捏造缺失的层。以下是 agent 的工作，不是让用户填表。

头发专项先完整阅读 [头发渲染规范](hair-rendering-standard.md)：以实际参考实现的头部空间高光、距离场投影和受控眉眼补绘为设计基准，保留主刘海不透明、源眼着色/裁切与前后关系。装配/重载、静态看图和游戏性能分开；`preserve` 或仅有 helper 不算达到规范。具体层路由填 `templates/hair-assembly.md`，不把通用图的 UV1 分支当唯一算法。

| 交付键 | 必做的模型判断与实验 | 不能冒充的结果 |
|---|---|---|
| `eye_layers` | 核对眼白、虹膜、瞳孔、绘制在贴图中的高光、实际叠层与眼睑遮挡。分别控制高光/阴影并拍正面、斜侧近景；检查双重高光、穿出眼眶和排序。只有单层时可实现有理由的单层近似，并记录深度局限 | EyeGlow 或整体提亮不等于层次；不强制生成四层眼睛或玻璃壳 |
| `hair_clumps` | 看发束 UV/遮罩，确定使用 UV0/UV1/自制方向数据；制作成束而非整片塑料高光。单独开关高光，改变相机和光向；转头/转身另测高光是否错误锁在世界轴 | 默认高光纹理、固定世界 Y 偏移、头发颜色正确不能证明成束效果 |
| `stocking_edge` | 核对袜下是否有皮肤及纹理是否已合成肤色。分别做边缘色与高光的开关对照，正面/斜视腿部近景；白丝使用本模型颜色，避免通用黑丝 Tint。弯腿再测方向是否随变形 | 边缘厚度感不等于透射；不能无底层皮肤就降低透明度；常量纤维方向不是蒙皮切线 |

头发/刘海还须按 [专项流程](hair-bangs-workflow.md) 分别处理宏观法线、高光、投影与局部半透，不能只对后发开启高光。已知旧工具风险仍须处理：眼睛 Modulate 强度需要以白色为关闭中性值，不能照搬加法乘零；Hair 的世界 Y 已换成 HairUpWS 点积接口，但默认世界 Z 不是自动头骨驱动，旧角色仍需新建材质验证；Stocking 常量局部方向不跟随每根腿骨；布料/丝袜附加 Emissive 高光不自动继承灯光强度/阴影。这些脚本是候选，契约不是 shader 效果完成证明。执行 agent 必须适配、验证或明确报告未完成，不能据“现成工具成功”验收。

## 最小交付结构与旧清单迁移

保留 delivery.v2，新增必填 `material_review_contract: 1`，按 templates/delivery.example.json 补三项 `material_features`，不是只加版本数字：

- `reviewed`：实际 slots、模型依据及 evidence、关联专项 effects ID、观察字段。effects 须 reviewed 且要求 A/B，覆盖目标槽；同一报告/候选至少有两个 Lit 观察机位，agent 负责确认是可辨细节的正面/斜侧近景而非随意改相机名。原 effects 的已看图与匹配 A/B 检查仍有效。
- `not_applicable`：确无对应表面时 slots=[]，附源模型审计/设计证据，不可因工具没有实现而使用。
- `accepted_limitation`：实际槽、具体缺口、证据与用户 `scope_approval`；不把该项宣称已实现。用户已要求的效果不自动降级。
- `pending/blocked`：保留 next_action 与原因，材质交付 incomplete。不得用一个“全角色贴色”条目替代三项观察。

观察字段分别为：眼睛 `geometry_layers/highlight_shadow/side_view`；头发 `uv_direction/clump_shape/view_light_response`；袜类 `surface_layers/edge_color/highlight_response`。可以共享真实共用算法的 effect，但每类仍需具体区域观察。

## 默认曝光不变

Open World 默认太阳、场景/工程曝光为基线。`exposure_ev100: null` 对单 case 和 A/B 都有效，不要求校准报告、固定 EV100 或最小像素尺寸。A/B 保持同一曝光策略，等待自动曝光稳定；形状、层次和高光不能只按整体亮度判断。只有明确诊断需求才临时选固定曝光，不为启动实验反复调曝光。

## 描边和边缘光的游戏可用性

`material_acceptance` 明确为 `static_lookdev` 或 `game_ready`。静态完成不自动升级游戏可用。选择了描边/边缘光时，scene_effects 对应条目必须有独立 `game_validation`：

- 静态范围允许 pending/blocked，但须 reason 和 next_action，并在交接明确未经游戏验收；没有动画不影响静态 lookdev。
- 声称 game_ready 时须 reviewed，`checks` 引用以下六项 `kind=material_game_test` 报告；报告格式见 templates/material_game_test.example.json。每项含具体观察、reviewer、已登记原始证据 ID 及当前资产组合指纹；不能只填成功勾选框。

| 检查键 | 执行与验收 |
|---|---|
| `occlusion` | 在获准实验实例中加前景遮挡，测试角色完全/部分遮挡、发梢、眼睛与透明层。深度 rim 必须结合 SceneDepth 的可见性，而非只看 CustomDepth/Stencil；不允许隔墙亮边 |
| `distance_lod` | 近/中/远镜头、不同 FOV 与实际 LOD 切换；检查描边厚度、重复轮廓、面部黑块、rim 爆亮。不能只拍一个全身机位 |
| `motion` | 播放已有动作并移动/转动角色、移动相机；观察闪烁、时域拖影、断边、动态轮廓与部位脱节。无动作则待测，不伪造通过 |
| `lighting` | 默认日光为主，另测侧/背光与遮阴；区分有方向性的边缘光和无方向描边，避免用发光遮盖错误光向 |
| `multi_instance` | 至少两个实例交叠、不同 stencil/材质分配和透明物遮挡；检查串色、后处理误选、与工程现有 stencil 冲突 |
| `performance` | 相同硬件/镜头路径/动画/角色数/物理/分辨率/画质/曝光策略，逐项关/开及最终组合测试。测试前读回 t.MaxFPS=200、VSync关闭；不擅自永久改项目配置。记录预热、时长、样本、Frame P95/P99、Game/GPU P95，原始 trace/CSV；预算由目标平台确定 |

性能报告 measurements.off/on 字段见模板。校验目标开启版本 Frame P99 和增加的 GPU P95 是否超过显式预算，不以平均 FPS 或限帧60时的数字宣称无开销。GPU 分位数差只是同条件粗对照，不是精确逐 Pass 耗时；必要时用 GPU profiler 确认。跨场景/后台负载变化要重测，不能把一次小场景结果推广成任意关卡可用。

`active_effects` 记录实际开关读回：off 为空，on 与报告 effects 一致；先独立测 outline/rim，再测最终组合。game_validation 的最小结构为 `{"status":"reviewed","checks":{"occlusion":"遮挡报告ID","distance_lod":"距离报告ID","motion":"运动报告ID","lighting":"光照报告ID","multi_instance":"多实例报告ID","performance":"性能报告ID"}}`。这些 ID 都先登记进 delivery.evidence；不能将同一 performance JSON 改引用名冒充另外五种测试。非性能报告保留模板的 schema/project/effects/check/passed/reviewer/observation/evidence/asset_sha256，移除 measurements/budget 并写出实际步骤及观察。

报告引用的原始截图/视频/CSV/trace 在 delivery.evidence 中登记绝对路径及哈希；同时记录 mesh、材质实例/父图、runtime BP 等实际依赖指纹。检查器只验证结构、来源、预算及所选资产匹配，不能代替看视频、判断遮挡正确或证明人工记录真实。

现有自动采集器仍以静态材质图为主；本轮提供执行规范与交付校验，并不假装已自动生成遮挡物、播放动作或采集全部性能测试。执行 agent 在用户指定工程的隔离版本中使用现有测试工具或最小适配实现，不另建项目、不操作用户当前关卡。
