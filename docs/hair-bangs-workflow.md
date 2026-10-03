# 头发与刘海：法线、高光、投影、局部半透

首组日光基线后执行，在静态材质交付前分别作出四项决策，不能用“头发颜色正确”或“已建刘海材质”代替。**先完整阅读 [头发渲染规范](hair-rendering-standard.md)，以 MultiAgentsForGPT 实际头发/投影/眼层方案为默认设计基准。** 文章算法只作其它候选的背景，不优先于已核对的实现。适用目标图可选；有图时检索 catalog 的 hair/face/eye 区域，比较刘海高光范围、眉眼可见程度和额前阴影。无图依据实际模型与文字要求继续。

## 1. 球形法线：干净漫反射，不等于高光或球面贴图

先读实际头发/刘海槽与法线，确认是否已做球形法线映射，避免重复平滑。可选候选：

```text
Ns = normalize(Pws - HeadSphereCenterWS)
Ndiffuse = normalize(lerp(NsurfaceWS, Ns, SphereBlend))
```

球心与混合量按本模型头部体积拟合；只用于头发/刘海宏观漫反射，不强迫法线贴图、N·H 高光或其它材质共用这套法线。保留独立的高光法线选择并看图判断。PMX sphere map 是纹理混合输入，与球形法线不同。

现有 Master 的未绑定回退使用 `ObjectPositionWS + NormalSphereOffset`；有效 `HairBasisRuntimeValid` 时选择 `HeadSphereCenterWS`，不能把它笼统描述成永远没有头骨球心。默认 `[0,0,65]` 和 hair 预设混合量不是模型校准。它影响自定义 toon 漫反射，不等于改好了引擎原生 PBR Normal。旧刘海候选未接入这套驱动，不作为规范方案。

执行 agent 选择已烘焙且随蒙皮变化的宏观法线，或在独立头发父图中接入经校准的头部球心；运行时计算时用每实例头骨位置与方向更新，不能固定世界坐标、整个角色包围盒中心或共用 MPC。头骨轴/偏移来自当前绑定姿态，不能把骨骼任意局部 Z 当人体向上。长马尾、编发、物理发束不能全按头盖球面平滑：按真实区域遮罩控制混合，保留发束表面/切线；转头与发束变形是不同验证。无动画先验证静态，动态跟随单列待测。

## 2. 发束高光：头部空间基准与有据的 UV 替代

新角色优先采用规范中的**头部空间高光带**：头骨高度/视线俯仰确定亮带位置，宽度/侧向弧度确定形状，独立高光法线的 N·H 与真实纹理调制发束细节。`head_band` 仅是部分适配器，差异和实现边界见规范；新模型不能只选 `preserve` 然后宣布高光完成。已认可的 UV 高光可有据保留，以下是该替代路线的计算，不强制所有模型重做直 UV1：

```text
Vws = normalize(CameraPositionWS - Pws)
Lws = normalize(指向光源的世界方向)
Hws = normalize(Lws + Vws)
offsetV = -dot(Vws, HairUpWS) * HairSpecOffsetSpeed + HairSpecOffset
highlight = sample(SpecMap, uvHighlight + (0, offsetV)).rgb * HairHighlightTint
highlight *= saturate(HairSpecMinIntensity + pow(saturate(dot(NspecWS, Hws)), HairSpecPower))
highlight *= HairHighlightStrength
```

参考的世界 Y 是其坐标约定，不能直接套到 UE。新 Master 为 `HairUpWS` 点积，默认 `(0,0,1)` 仅是 UE Z-up 静态起点；有效头骨驱动时改用 `HairUpRuntimeWS`。可迁移共享组件与 `head-hair` 入口见下一节，不把参数存在当作新模型动态验收通过。符号按真实 UV V 方向验证；L/V/N 必须同空间，L+V 近零时自定义实现需提供稳定退化处理。

- 高光贴图与 UV1 必须实际有效：检查发束是否打直、V 是否沿发束、图案是否落在刘海及其它目标发束。UV1 不存在、复制了不合适的 UV0 或贴图全白/全黑时，不能继续宣称成束高光。可在新 mesh 变体保留 UV0 并生成独立高光 UV/遮罩，或选择基于真实切线/遮罩的替代图；仅因不能原样套公式不停止在基础贴色。
- 刘海与后发分别检查实际槽、父图、`DetailMaskTexture` 和参数读回；不能只对后发开启。旧 Master 除 `HairMode`、`HairHighlightStrength` 外还乘 `NPRSpecularStrength`、光照门控及输出混合，任一归零/被弱化都可能导致不可见。缺资源降级只是排错，不是效果完成。
- 高光不明显时依次查有效输入/UV、开关与完整乘法链、法线/N·H、光源方向，再调强度、范围和 tint；用临时隔离诊断变体定位门控，不永久去掉光照约束制造常亮亮条。有目标图时确认横向宽度、沿发束覆盖和柔和边界，而非只增亮。
- 先在角色正面左侧 45° 日光下比较关/开高光；正常后补相机上下移动、侧视及转光，确认亮带沿头发移动而非按世界横轴漂移。转头/转身、发束物理变形需另测；头骨轴本身不等于每根发束的变形切线。

## 3. 刘海投影：实际接收范围与深度

默认采用规范中的五角度距离场投影：真实几何遮罩转换有符号距离，按当前头部基轴/主光插值距离后阈值生成单一阴影边界，再限制真实额头接收区域。独立脸部接收层与原 Face SDF 分开；真实烘焙、receiver 校准和额外层装配都要完成，helper 不会替你挂载。

文章的视图空间偏移/模板双 Pass 和旧源码的透明几何投影不是当前默认方案。`create_bang_passes` 因已报告渲染错误继续禁用；不能改常量光向或调 opacity 后宣称旧方案已修复。需要其它投影路线时给本模型的依据并独立验证，不能把 Face SDF 当已包含刘海投影，也不能硬编码参考角色的 stencil。

## 4. 刘海局部半透：只透眉眼，不整片透明

默认采用规范中的**刘海深度代理 + 受控眉眼补绘**：保留原 Opaque/Masked 刘海，代理仅显示实际刘海几何并写 CustomDepth/Stencil，额外透明层绘制眉/睫/眼而不是头发。仅当目标在刘海后方、场景可见表面为该刘海且接近正面时补绘；无需排除原不透明刘海区域，也不宣称真实光学透射。

**不要复用旧半透实现。** 旧 overlay 是另一套透明头发近似，不能与受控眉眼补绘混淆。当前 outline Overlay 也不等于刘海装配接口。眼层需复制完整原着色/参数，源 Masked 裁切和 AlphaScale 保留；两眼共享 UV 时分别用 R/G，后方眼白必须排除前方虹膜，防止双重混白。不能以提高透明度或眼睛亮度代替遮挡修正。

新方案在独立版本按 `templates/hair-assembly.md` 记录真实组件/section 路由和挂载回读，确认只在实际眉眼区域变化、没有叠白/背景泄漏/前景穿透后再采用。`specials.bang` 旧构建请求仍失败；不要删除需求后宣称完成。文章的真正刘海双 Pass 只可作为有据的另选方案，不能将其“原层排除”要求套给本规范。

执行 agent 在独立 BP/组件中建立共享姿态的 FringeDepth/BrowPeek/FringeShadow/EyePeek 等实际层路由，核对各 LOD 的 section→material 映射，不假定二者编号相同。运行时提供 Head/Forward/Left/Up/球心及 Valid；共享驱动目前只为头发自动提供球心/上轴，其它层需适配。能力不足时做最小适配或记录具体阻碍；只建材质不算完成，也不能原样复制参考 Actor 的固定编号/重复 tick。

## 5. 小实验与交接

可复用独立工程的已审阅做法见 `docs/reference-implementation-transfer.md`：`head-hair` 的 opt-in `head_band`、五角度距离场转换与 `fringe_distance`/`eye_peek` 显式接线 helper。UV1 正确导出不证明各岛根梢方向/尺度适合统一 V 平移；不合适时使用真实遮罩约束的头部空间带状高光，不复制 matcap 灰度当 atlas。投影先插值距离场再画边界、仅接收实际额头；共享 UV 的眼睛按本眼 R/G 孔径选取，保留虹膜遮住眼白的关系。helper 不自动建额外 Pass，旧半透不解禁，静态候选不冒充动态通过。

在现有指定工程的新材质版本内复用认可 mesh，沿用 Open World 默认曝光与清晰原尺寸 Lit 截图。四项逐个关/开，最后组合；复用全身图并只补必要脸发近景，不增加所有光向的大矩阵。

分别在 material-design/material-review 与 delivery.effects 中记录真实槽、输入/UV、坐标与头骨/光源驱动、父图/额外 Pass、挂载读回、同条件图及当前缺口。`hair_clumps` 的已审核条目必须说明刘海覆盖情况，不能只写后发；投影和局部半透各有明确决策与证据。缺动画不阻止静态实现与透明遮挡检查，但动态排序、转头跟随、物理发束和游戏性能保持待验。

采用半透/额外 Pass 后记录 overdraw、排序、远近 LOD 与遮挡风险；同条件关/开测 GPU/Frame 开销，游戏验收沿用现有性能预算及 `t.MaxFPS=200`。源码/逻辑测试不证明 shader 已编译或画面已完成。

## 6. 可复用头骨驱动入口

复用 Face SDF 的同一个 `PMX4UEFaceSDFComponent`（已有宿主用对应适配），不另建一套 tick/全局参数。头发不依赖 SDF 纹理，也不要求脸部启用 SDF。`bDriveHair` 默认关闭，仅 `HairMaterialSlots` 中、父图显式有 `HairBasisRuntimeValid` 的槽会被接管。复用已在 Character 上驱动脸部的组件；不要另加第二个组件抢同一 MID。

校准输入是**导入绑定姿态的组件空间**，不是当前动画位置，也不是任意骨骼局部轴：

```text
localCenter = inverse(ReferenceHeadCS) * SphereCenterReferenceCS
HeadSphereCenterWS = ComponentToWorld * CurrentHeadCS * localCenter
HairUpRuntimeWS = normalize(ComponentWorldRotation * CurrentHeadRotation
                           * inverse(ReferenceHeadRotation) * ReferenceHairUp)
```

球心先从实际头部几何与绑定姿态提出起点，沿用有效头发法线时不重复修正，再由日光画面拟合。骨骼枢轴不一定是头部体积球心；示例零位置绝不自动批准。位置跟随平移/旋转/缩放，上轴只取旋转并归一化。头骨缺失/失效时 `HairBasisRuntimeValid=0` 走未绑定分支；禁用/解绑恢复组件原材质，不修改 mesh 默认槽。

1. 复制 `templates/head_hair.example.json`，填写真实 mesh、刘海/头发槽、HeadBone、校准上轴与球心及证据，审核后设 `reviewed=true`。明确起点与视觉接受两种状态。
2. 编译/reload 已选运行时提供方。工单设置 `pmx4ue.head_hair_profile=<审核 JSON 绝对路径>`。
3. 运行 `python pmx4ue.py run --config <工单> --stage head-hair` 查看计划，再加 `--execute` 执行。
4. `head_hair.json` 输出独立头发父图/完整实例继承链、`component_overrides` 和校准 profile。共用父图只复制一次；源 mesh/材质指纹不变，不保存关卡，也不替换其它槽。
5. 在自有预览或获授权角色实例，通过 `tools/ue_head_hair_binding.py:apply_binding(report, actual_mesh_component, shared_head_driver)` 挂载；这是实例操作，不保存源资产。正式角色将同等设置固化进 BP/组件。保留已审阅的 Face 双轴，不因头发接入重置它们。单开材质或普通 AnimBP 预览没有该组件，不等于已挂载。
6. 原图修补器 `ue_head_hair_runtime.py` 只接受经核对的旧球心/世界 Y 偏移拓扑，在复制图插入运行时分支，Valid=0 保留原图，**不改原 UV、贴图、完整高光门控、透明或 SDF 计算**。新 Master 已包含同协议。非匹配图明确失败，agent 根据实际图适配，不能为了通过删除高光或改接错轴。

运行报告只是 `built_needs_runtime_visual_review`，必须检查实际动画→材质读回、转身/双实例隔离、缺骨与恢复，然后固定正面左侧 45° 日光近景做 A/B，确认头盖/刘海漫反射、高光范围与相机上下移动。原图回退只是安全机制，不证明原世界 Y 公式适用于角色。

### 成本控制

- 先读真实两个/少数目标槽、纹理与关键门控；脚本/数据检查优先。小运行时探针用一段已有动画和两个实例、约 60 帧，不启动衣裙/头发物理、不测全角色矩阵。
- 首轮仅一个共享父图和必要实例；复用认可 mesh，不重导入、不重做 IK。只改球心/轴时不顺带改高光强度/宽度，定位后再作单变量 lookdev。
- 相同光照/机位先用 2 张 Lit 局部关/开图；仅必要时补一张组合或失败诊断，不默认生成 normal/unlit、七光向乘多相机。
- 编译并行数可按宿主资源限制，独立进程参数不改全局工程设置。持续缓存写入/507 空间告警时停止扩大渲染实验，记录环境原因，不清理用户缓存或改曝光凑结果。
- 半透与投影继续独立验证；旧错误实现保持禁用，不能因为头骨驱动通过而重新开放。发布写清数据/视觉/性能各自状态，不用一个 pass 标记混称全链完成。
