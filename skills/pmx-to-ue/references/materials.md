# 材质：agent 判断，脚本构建

开始本领域工作时还需完整阅读 [材质迭代与交付](../../../docs/material-iteration-and-delivery.md)。按版本/API 风险选用 `material-preflight`；第一轮基线尽早截图，材质实验使用 `material-build` 复用已认可 mesh，最终用 `delivery-check` 检查明确版本组合和证据。缺资源关闭功能只算排错，必须跟进 `material_debt` 与设计表目标。不要通过删掉源输入、缩减交付范围或勾选审核标记制造完成。

默认交付目标是角色级 lookdev，不是通用 Master 的基础贴色。材质设计前完整阅读 [material-families.md](../../../docs/material-families.md)，根据实际模型填写 `templates/material-design.md`：逐类确定脸部、头发/刘海、眼睛各层、袜类、不同织物/硬表面和轮廓效果的计算、父图/Pass、输入与验收。颜色正确只算基线；不按 Master 个数考核，但不同行为必须真正实现。文章/案例用作方法参考，不能假定其轴、UV、Pass 或参数适合新模型。

目标图按需完整阅读 [目标图驱动的材质迭代](../../../docs/target-image-lookdev.md)：先从 PMX 素材根目录（含 targets/参考图 等子目录）主动发现，离线生成 catalog；实际看图后按丝袜、布料、脸部、全局等区域建档。每轮设计、渲染或委派前用 query 按标签/特征定位原图与区域，再与实际截图对照；目录线索不代替分类，不将源纹理/故障图自动当目标。无适用图时依据 PMX、纹理和文字要求继续；不免除实际渲染结果的视觉检查。

选择算法前按同文“先核对实际资产，再选择算法”检查必要的几何层、槽/UV、RGB/Alpha 与变形条件。把事实、实现假设和验证办法分开；不能从“丝袜看起来薄”直接决定透明/透射，也不能因缺少检查结果就断言没有皮肤底层。检查范围围绕候选方案，不重复无关审计。

运行 `material-draft`，由 Blender manifest 的真实材质槽生成未绑定草稿。检查源贴图图像、PMX 槽参数、UV、透明类型和参考效果，然后填写 material_map。文件名只提供候选，不能据 `_N` 等后缀自动绑定法线或打包通道。

`presets/materials.v1.json` 提供可编辑的起点；`mmd2ue_core.normalize_material_map` 是规范化接口。按需读取该函数和 `validate_material_map` 的字段约束，不另造不被构建器消费的配置字段。`material-check` 执行纯 Python 的槽覆盖与审核校验；再设置 `pmx4ue.material_reviewed=true`，执行 `ue-build`。此阶段导入选定的 FBX 与贴图，创建材质，不配置或保存用户场景。

`parent: stocking/cloth` 已接入专用图构建；`parent_assets` 可注册 agent 编写并保存的其它专用父图。未知/冲突父路由、专用图缺输入会失败，不回退 Master。专用图用自己的参数 profile，不拷贝通用图的全部开关；真实能力和配置语法见 material-families。轮廓/后处理/刘海额外绘制层不是槽父材质替换，需要单独接入和验证。

新变体必须使用空命名空间。构建失败产生部分资产时，先检查日志，选择新版本或得到明确范围后清理，不让重复导入覆盖已有角色。

`ue-validate` 检查槽绑定、图连接、纹理配置。报告中 `compile_check_required` 必须另外用插件 `PMX4UEAgentMCPTools.inspect_material_compile` 检查；图连通并不证明 shader 编译成功。最终以 Lit 外观和有必要的不同光照角度检查为主。Unlit/WorldNormal 非必要不拍；出现贴色或法线疑点时，通过 `diagnostic_captures` 定点补一张，不在全部相机、光照和候选之间重复采集。

进入视觉阶段前完整阅读 [agent-material-workflow.md](../../../docs/agent-material-workflow.md)。使用审核的 v3 `material_preview.example.json` 和 `material-preview` 阶段：自有可见编辑器直接加载安装的 Open World 日光地图，不复制或保存自定义预览地图；在相同视角/光照下做材质 A/B，等待角色实际贴图 mip 驻留后取实测视口 backbuffer 截图。不要调用旧 current-level setup，也不要因为会话缺少截图 MCP 工具而停止；插件公开方法可直接通过 UE Python 使用。离屏截图或仅有高分辨率 PNG 不作材质验收。必须在原尺寸打开全身与局部近景，模糊时按流程排查贴图、LOD、时域抗锯齿与取景；无法出清晰图则记录阻碍，不能以编译结果签收。

默认在自有编辑器中直接加载 Open World 日光场景，不用偏暗的空关卡单灯作为主要验收。保留默认太阳作环境核对，材质主观察光按模型朝向调为正面斜侧；沿用场景/工程曝光，单 case 与多 case A/B 均允许 `exposure_ev100: null`，不要求独立校准报告。先确认环境与取景可用；仅在具体诊断或受控亮度测试需要时选择固定曝光，不反复调曝光作为启动门槛，也不要调材质发光补救错误照明。v1/v2 示例、旧 profile 迁移和环境加载限制见上述视觉闭环。

逐项处理未分类贴图，记录纹理→槽→UV/通道证据；填写 `templates/material-review.md`，实际打开截图后才判断视觉。用户要求的效果即使属于可选功能，也要做隔离对照或明确列出缺口。没有动作不妨碍这些静态测试。所有角色先将主光设为从**角色实际正面左侧 45°**射来，按当前 mesh 世界前向和模板太阳初始 yaw 换算 `yaw_offset`，不能把 45° 直接当偏移量或选背光；具体换算见 `docs/agent-material-workflow.md`。在此光下确认外观正常并留图，异常先修复；之后才新开转光运行，记录阴影、高光及局限。无需另加自动方向校验；七角度脸部扫描无需乘到所有材质族。

## 按需效果

有头发/刘海时先完整阅读 [hair-rendering-standard.md](../../../docs/hair-rendering-standard.md)，再读 [hair-bangs-workflow.md](../../../docs/hair-bangs-workflow.md)。以已核对的独立工程头发方案为默认设计：球形漫反射、头部空间高光带、干净距离场投影、刘海深度代理和受控眉眼补绘。保留主刘海 Opaque/Masked，不要求原层排除；补绘保留完整眼着色、原裁切、分眼 R/G 与前后关系。用 `templates/hair-assembly.md` 记录真实层/section/LOD 与运行时读回。`head-hair` 只复制头发图并接入球心/上轴，helper 不是完整装配；缺接口时做最小适配，不能默认 preserve 就交付。旧半透继续禁用，先小数据检查再少量日光 A/B，不重跑全角色。

“按需”不代表默认不做：描边和边缘光都要在角色设计中有明确决策。完整阅读 [场景效果闭环](../../../docs/scene-effects-workflow.md)，使用主流水线的 scene-effects-build 构建选定候选，在自有日光预览实际挂载、截图比较，填写 delivery.scene_effects。用户要求的效果不能以 optional 为由省略；不适用时附模型证据和理由。

脸部存在时先读 [脸部阴影执行流程](../../../docs/face-shading-workflow.md)。SDF 是算法选择，但脸部阴影不能无限期搁置：第一组基线图可用后开始，静态材质交付前完成真实贴图或验证替代方案。`face-sdf` 是运行时驱动接入，不生成贴图；烘焙和新数据检查工具的命令见该流程。交付 v2 的 `face_shading` 必填，不能将全白 Neutral 或关闭的开关当成效果实现。

若用户已认可某版脸部阴影观感，先完整阅读 [Face SDF 观感基线与响应选择](../../../docs/face-sdf-lookdev.md)：固定该版图片、贴图、UV、材质公式及光照条件，优先复现再单变量调整。不要仅凭“数学角度更正确”替换已认可的阴影曲线；也不要把美术化响应冒充烘焙编码一致。新版本 `material_map.json` 可在 `policies.face_sdf_light_response` 显式选 `cosine_half_art`，默认是 `linear_azimuth_v1`；必须用 UE 材质验证的 `face_sdf_response` 实际图连接读回，不可仅凭声明放行。

Face SDF、轮廓、丝袜/布料专用材质、头发高光按模型与目标选择，并非每个 PMX 都必须具备；但“可选”不能成为存在相关材质却不分析、不实现的理由。相关工具已复制到 `tools/legacy`，根据材质设计表选择、改写和验证：

- `tools/blender_face_sdf_probe.py`：按真实脸部槽名探测 UV/朝向。
- `tools/legacy/blender_face_sdf.py`：显式传入 face slot 和 model-faces，独立后台场景烘焙。
- `ue_feature_outline.py` / `ue_feature_depth_rim.py`：会影响指定场景实例，先确认用户允许的测试场景，不能作为基础导入的隐藏副作用。
- `ue_feature_cloth.py` / `ue_feature_stocking.py`：先判断真实槽、通道、法线与纤维方向，再构建；缺资源优先考虑基于本模型生成/适配，暂退基础材质仅算 baseline，不算完成。脚本中旧默认颜色和 UV 不是当前角色的审核结论。

法线发黑先做零模拟对照，再分别检查拓扑绕序、变换 handedness、法线/切线与材质，不能直接反转所有法线。受物理影响只在模拟路径出现时，先查模拟→骨骼变换，不重写原本正常 mesh。

## 动画中的面部 SDF

材质编译通过不代表面部朝向随动画更新。启用 Face SDF 的游戏角色还应按 `docs/face-sdf-runtime.md` 检查头骨驱动、参考姿态轴校准、世界/模型空间契约和每实例参数隔离。审核 `templates/face_sdf.example.json` 的角色副本，设置工单 `pmx4ue.face_sdf_profile`，执行 `face-sdf` 阶段，生成独立材质与预览 BP。插件含 `PMX4UEFaceSDFComponent`，MMD2UE 使用现有 `MMDFaceSDFComponent` 适配，不安装重复插件。不要把 Actor 朝向当头骨朝向，或将已是世界空间的轴再次 Local→World。验收应在拥有驱动组件的角色实例进行，不以普通 ABP 预览代替；新角色必须重新确认双轴与视觉效果。
