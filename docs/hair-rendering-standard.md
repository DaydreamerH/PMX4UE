# 头发渲染规范：头部空间高光与受控刘海补绘

本规范以 MultiAgentsForGPT 的实际头发版本 v9、干净投影 v10、眼层修正 v12 为实现基准，不以早期文章的双 Pass 示意或旧 `create_bang_passes` 为默认方案。它规定 agent 应实现的计算、实际装配与验收，不表示便携工具已经自动完成这些内容。参考工程仅作只读来源，新工程不依赖其文件、插件或角色资产。

适用于有对应头发/刘海/眉眼结构的角色。不存在的结构有据 N/A；模型不适用时记录具体原因和替代方案。目标图可选，有图时按 catalog 的 hair/face/eye 区域比较，无图仍按实际模型执行。不得将单一 Master 贴色或保持原图不动当作已达到本规范。

## 1. 基准与模型适配边界

| 内容 | 应保留的基准行为 | 必须由当前模型决定的内容 |
|---|---|---|
| 漫反射 | 校准头骨球心随实例和动画变化，球形宏观法线与表面细节分开 | 球心、球面混合区域/强度、长发或物理发束的保留范围 |
| 高光 | 头部空间连续亮带，随视线俯仰移动，以 N·H 和局部纹理调制 | 高度、宽度、侧向弧度、强度、颜色、法线混合和覆盖 |
| 刘海本体 | 保留原 Opaque/Masked 着色、真实 Alpha 裁切和头发高光 | 实际 Blend Mode、裁切输入和阈值，不默认改成 Translucent |
| 刘海投影 | 五角度距离场先插值再阈值，独立限制真实额头接收范围 | 几何烘焙、UV、光向/仰角、接收遮罩与强度 |
| 眉眼可见性 | 刘海深度代理 + 深度受限的眉/睫/眼层补绘 | 槽/section、独立模板编号、深度间距、侧视渐隐与权重 |
| 眼层关系 | 本眼 R/G 孔径选择，保留源着色、源裁切和虹膜遮住眼白的关系 | 两眼身份、左右轴符号、孔径、前方虹膜与其它遮挡 |

不照搬参考角色的 Head 偏移、槽号、Stencil、.50 权重或太阳方向。参考实现的简单纹理亮度调制是美术近似，不是现成的发束 atlas，也不是物理各向异性 BRDF。

## 2. 先做头发主体：球形宏观法线 + 头部空间高光

先复用已认可 mesh、UV 与其它材质，在独立父图/实例上实现，不重导骨架、IK 或物理。分清后发与刘海槽，两个区域都要有高光观察。

```text
D = Pws - HeadWS
Nsphere = normalize(Pws - SphereCenterWS)
Ndiffuse = normalize(lerp(Nsurface, Nsphere, diffuseBlend))
Nspec = normalize(lerp(Nsurface, Nsphere, specBlend))
height = dot(D, HeadUpWS)
lateral = dot(D, HeadLeftWS)
bandHeight = Height - dot(Vws, HeadUpWS)*ViewShift - Curve*lateral*lateral
band = exp(-2*((height-bandHeight)/Width)^2)
lobe = saturate(MinIntensity + pow(saturate(dot(Nspec, normalize(Lws+Vws))), Power))
highlight = band * lobe * strandWeight * HighlightTint * HighlightStrength
```

所有方向同为世界空间，长度为厘米；提供归一化/零长度保护。`Curve` 为 1/cm，按当前头部宽度拟合；可有据设为零，而非复制参考固定值。若以 SphereCenter 为高度原点，显式转换 Height，不混用 Head 枢轴与球心。漫反射和高光混合分别选择；现有 toon 球形法线不是改写 UE PBR Normal。

`strandWeight` 首选已审核的发束遮罩。参考 v9 实际使用颜色纹理亮度和保底值调制，没有依赖直 UV1；允许 agent 在当前纹理确有发束信息时使用这种显式近似，记录输入、下限和局限，不把它命名为美术高光贴图。需要更丰富分束时再生成真实遮罩；sphere/matcap 不可直接冒充 atlas。不要因缺直 UV1 而无限停留在不可见的旧 UV 高光。

新角色优先拟合本规范的头部空间亮带。已有认可的 UV 高光可有据保留为替代；`preserve` 是工具兼容/回退模式，不是新角色高光已完成的默认结论。完整检查 HairMode、HairHighlightStrength、NPRSpecularStrength、光照门控、PBRBlend、OutputGain 与末端钳制，避免只提高强度而亮带仍未进入最终输出。

当前 `head_band` helper 提供球心相对高度、视线移动和显式遮罩，**未实现参考的侧向弧度、Head 枢轴高度和颜色亮度保底调制**；选用时记录有据差异，必要时适配复制图，不声称公式完全相同。按拓扑/参数接口适配，不照搬参考脚本按编辑器节点坐标定位的写法。

## 3. 刘海装配：保留头发，补绘眉眼

此处“局部透刘海”是受控的遮挡后补绘近似，不是修改刘海真实透射。**保留原不透明刘海，不要求挖掉其眉眼区域**；额外透明层绘制的是眉眼，不是另一层透明头发。只有另选并验证真正的头发双 Pass 算法时才讨论原层排除，不能把两套策略混合。

| 层/组件角色 | 实际显示的几何 | 渲染策略 |
|---|---|---|
| Body / Hair | 原角色与认可头发槽 | 主 Pass 保持原覆盖/着色，主眼睛高光层不擅自删改 |
| FringeDepth | 仅实际刘海 sections | 不参与主颜色/普通深度 Pass；写专用 CustomDepth/Stencil，保留真实刘海裁切形状 |
| BrowPeek | 实际眉毛、睫毛 sections | 受深度/模板/视角限制的额外透明补绘，源 Alpha/颜色保留；简单 Unlit 仅可作为明确的眉睫近似 |
| FringeShadow | 仅脸部接收 sections | 距离场阴影叠层，保持原 Face SDF，不把阴影画到眉眼/脸颊 |
| EyePeek | 实际虹膜与眼白 sections | 复制完整原着色，仅改额外层覆盖，保留本眼孔径和前后关系 |

额外组件共享主 mesh 的最终姿态（LeaderPose 或等价方式），不各自播放动画/模拟；禁用碰撞、额外 cast shadow，检查 bounds 与各 LOD。按实际 section→material 映射隔离几何，不能只用“其它槽透明”或组件全局 Stencil 冒充过滤；不要假定 section index 等于 material index。读回各 LOD 的可见 section、材质覆盖和主/深度 Pass 开关。

模板编号从工程真实占用中分配，同编号的其它实例可能误匹配；多角色交叠必须独立核查。CustomDepth 的透明写入、RHI 与项目设置能力要查当前引擎；不能为演示擅自永久改项目设置。深度代理不能画原刘海没有覆盖的空隙。

## 4. 补绘的计算与眼层关系

```text
side = dot(Pws - HeadWS, HeadLeftWS)
aperture = 按 side 和已校准左右身份选择本眼 R 或 G
gap = PixelDepth - FringeCustomDepth
coverage = 原 Masked 时 step(SourceClip, SourceAlpha*AlphaScale)
           连续透明源时 saturate(SourceAlpha*AlphaScale)
opacity = coverage * aperture * PeekStrength
          * stencilMatch * behindWindow * frontFade * sceneDepthMatch * runtimeValid
```

深度必须是同单位/同空间；`sceneDepthMatch` 检查当前可见表面确为该刘海，前景遮挡时补绘关闭。`behindWindow` 只接收处于刘海后方的目标，上下限来自真实间距；`frontFade` 正面生效、斜侧渐隐。眉睫可不需要分眼孔径，但仍须同样的可见性限制。禁止为修孔径错误全局扩大深度窗口、提升眼亮度或移动/放大眼睛。

两眼共用 UV 时分别烘焙 R/G，不取 min 或 union。眼白遮罩还要排除前方不透明虹膜及真实眼睑遮挡；相同权重不等于能避免两层叠白。另可先按正确深度合成整眼再混合一次，须记录验证。复制父图与全部有效实例继承/纹理/标量/向量，保留原 BaseColor、光照、高光和 Emissive 连接，不退化为颜色图发光。

源 Masked 转补绘 Translucent 时仍保留原裁切阈值与 AlphaScale，避免原不可见边缘变成半透明灰圈。`eye_peek` helper 要显式接 AlphaScale、SourceClip、CoverageMode（1=源 Masked 二值覆盖，0=连续覆盖），未知参数不猜。旧绑定缺这三个输入须适配后重建独立候选，不修改已保存材质。静态正面孔径不自动适应眨眼/表情/眼球旋转。

## 5. 干净额前投影

从本模型真实刘海对接收面的遮挡烘焙 -90/-45/0/+45/+90° 遮罩，先转换有符号距离场；A.RGBA 为前四角度，B.R 为最后角度，B.A 为真实接收覆盖。按头部基轴与实际主光算 yaw，先插值距离，再 smoothstep 画单一边界，乘额头局部接收遮罩及方向渐隐。

不要插值二值图后直接叠灰块；不要改原 Face SDF 去隐藏刘海投影错误。固定姿态/仰角的烘焙有适用范围，转光/发束变形另验。工具只负责已有角度遮罩的转换，几何烘焙与 receiver 校准仍由 agent 按实际模型实现。

## 6. 接入顺序、能力边界与小实验

1. 核对当前头发/刘海/眉睫/虹膜/眼白几何、原 Alpha/UV、头骨轴与额头。填写 `templates/hair-assembly.md`，由 agent 从数据完成，不让用户填参数。
2. 先拟合头盖/刘海球形漫反射与头部空间高光；正面左侧 45° 日光下单项开关，通过后移动相机俯仰，再转光检查。长发单独决定宏观法线范围。
3. 保留已认可头发，分别完成刘海深度代理、眉睫补绘、分眼一致补绘、干净额前投影；每次只对一个缺陷作同条件对照，不同时改颜色/孔径/深度。
4. 统一运行时输入：HeadWS、校准 Forward/Left/Up、SphereCenterWS 与 Valid，复用同一次动画头骨采样。当前共享驱动只为头发自动提供球心/上轴；额外层的 Head/双轴、目标 MID 与姿态路由仍需宿主适配。缺骨时 Valid=0 关闭补绘/投影，不能照搬参考 Actor 的恒定 Valid=1。
5. 保存准确 BP/组件/材质组合后重载，读回全部槽/sections/原输入/驱动，确认没有修改源 mesh、Face SDF 或主眼层；填静态审核与待测项。

新 `head_hair.example.json` 显式选择 `head_band`，其 reviewed=false 和数值/遮罩仍是待拟合占位，不可直接执行；旧 profile 缺省 `preserve` 保持兼容，已认可效果可有据保留。

目前 `head-hair`、`fringe_distance_fields.py`、`ue_hair_reference_nodes.py` 是可复用的局部工具，**没有完整刘海装配的一键阶段**。缺接口时 agent 在目标工程的独立版本写最小适配；仅有 helper、材质资产或编译结果仍是 pending，不得以“未自动支持”直接放弃用户要求。旧刘海构建入口保持禁用。原参考 Actor 的重复更新、固定槽号/Stencil 与另一套协议不作为原样复制规范。

新模板提供装配记录而非伪造 runner 配置；delivery 的 effects 关联各项报告。未选择某层写模型/目标依据，有需求且未接入写 next_action，不以整体头发通过盖掉缺口。

## 7. 静态与游戏验收

初轮仅同机位/同主光的两张局部 Lit 关/开图；通过后按疑点补正面、斜侧、俯仰或转光，最后一张组合图。沿用 Open World 默认曝光、真实 mip 驻留和可见视口采集，不复制参考的保存地图/全矩阵采图方式。

- 高光：刘海/后发覆盖、亮带形状和成束信息、视线与光向响应，不是整体变亮；几何/眼形未因效果被修改。
- 投影：单一干净边界，实际额头范围，眼睛/脸颊没有额外灰块，Face SDF 仍保持认可表现。
- 透眼：与临时隐藏刘海的诊断图核对眼形/虹膜/眼白，不在正式组合隐藏刘海；没有叠白、灰圈、侧发漏眼、前景穿透。源高光层保持原路由。
- 游戏范围：连续转头/相机/遮挡、动画与表情、实例交叠、远近/LOD、静止与移动开销。静止也测同条件关/开和最终组合的 Frame/GPU P95/P99，测试前读回 `t.MaxFPS=200`；按目标预算，不把平均 FPS 当游戏通过。

参考记录仅支持静态候选，不能自动继承其动态或性能认可。本次流程更新不启动 UE，不修改参考或正式角色资产；源码/逻辑测试和真正 shader 编译、画面、游戏测试分开报告。
