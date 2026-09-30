# Face SDF：数据约定、质量诊断与迁移

本页约束工作流生成的新版本，不自动修改任何已有角色资产。工具能保证编码一致和暴露有损近似，不能保证几何烘焙天然具有目标画风。

## 1. 区分贴图编码、材质响应与观感目标

内置烘焙器的 R 是首次进入阴影时的 `θ/π`，即 `linear_azimuth_v1`。新 Master 使用头部正交前向/左向与指向光源的方向点乘：

`threshold = atan2(max(abs(dot(L, Left)), 1e-6), dot(L, Forward)) / π`

正面、45°、侧面、背面分别约为 0、0.25、0.5、1。侧向符号仍用于选左右 UV；头部双轴必须来自已校准的参考姿态并随头骨更新，不能拿 Actor 朝向冒充。公式在头部平面计算方位角，避免同一方位角因光线高度改变而被误解码；恰好头顶/脚底时方位角无定义，epsilon 仅防止数值异常，不意味着此效果能表现任意垂直照明。

旧 Master 的 `(1-dot(L, Forward))/2` 在 45°约 0.1464，和线性角度的 0.25 不同。将其用于 `linear_azimuth_v1` 贴图，是**有意改变明暗移动速度的美术响应**，不是匹配烘焙角度的解码，也不是 `cosine_half_v1` 编码贴图。若该观感已获认可，可保留并复现，按 [观感基线流程](face-sdf-lookdev.md) 标记为 `cosine_half_art` 并检查中间角度；不强制公式 A/B，更不得把贴图 manifest 改名为 `cosine_half_v1` 来通过检查。

通用构建器在 `material_map.json` 的 `policies.face_sdf_light_response` 中选择 `linear_azimuth_v1`（默认）或显式的 `cosine_half_art`，**构建时只生成一条响应路径**。后者仍使用 `linear_azimuth_v1` 烘焙贴图，不能改写 manifest 冒充 `cosine_half_v1`。`ue_validate` 沿阴影及高光阈值的实际连接读回响应；新交付检查要求 `face_shading[].light_response` 与读回一致、SDF 审计为 1024×1024、贴图源哈希与实际绑定一致。图结构读回不等于编译/视觉验收；未在 UE 编译或未采集多光向截图时仍需保留相应 pending 状态。

已有内置线性烘焙图可在审核质量后复用，但需新建/验证材质版本，明确选择严格角度还是美术响应。外部或手绘图先确认真实编码；声明 `cosine_half_v1` 不会自动转换数据，当前默认 Master 不支持直接匹配该图。应适配数据或新建匹配 shader 并留下实现、读回、视觉证据。不要仅改 manifest 字符串。

## 2. 不再静默丢掉再次受光的区域

单通道“首次阴影阈值”只能表达随角度单调变暗；真实几何可能先暗后亮。过去累积 AND 会丢掉这些再次亮起的区域。现在烘焙器保留每帧 mask，输出：

- `sweep_quality.json`：每帧损失比例、前方未受光比例、设置及原始 mask 哈希。
- `debug_RelitLost.png`：被这种编码丢弃的受光区域。
- `debug_FrontUnlit.png` 和 `debug_A_FaceMask.png`：帮助核对正面暗区、脸部覆盖及 UV padding。

默认 `--monotonic-policy reject`，任一帧损失超过有效覆盖的1%时停止最终贴图生成，状态 `blocked_nonmonotonic`。此阈值只是提醒检查的工程默认，不是美术合格标准；padding、眼窝/口腔或选错 UV 岛都可能触发。agent 应先定位实际区域，再修正脸壳/掩码/方向，或编辑符合目标风格的阴影序列，或选择可表达非单调变化的算法。不得为了通过而反复放宽阈值。

确有视觉依据接受首次阴影近似时，才使用 `--monotonic-policy first_shadow --review-reason "本模型具体观察及取舍"`；非默认容差也须记录理由。该开关只是允许导出候选，不代表验收。质量报告、相关诊断图及理由必须在脸部设计/交付的非单调审阅中引用。

## 3. 禁止通用鼻唇椭圆冒充角色高光

默认 `--highlight-mode disabled` 输出 G/B 零值，材质中高光强度保持关闭。仅当实际脸部 UV 和目标高光匹配，才可使用 `legacy_uv_ellipses` 并给审阅理由；更多情况下应为角色制作专门的鼻梁/嘴唇掩码。R 阴影可独立完成，不因未启用 G/B 而失败。

最大 UV 岛仍只是 A mask 的初始猜测，不能自动判定鼻口、脸颊。若原始侧光 mask 已是一条僵硬直线，只修正解码无法创造理想的鼻影或脸颊形状。agent 必须结合当前 mesh/UV 及可选目标图进行 lookdev，不能把通用烘焙当最终美术成果。

## 4. 交付检查与验证边界

按 [脸部阴影流程](face-shading-workflow.md) 在默认日光场景中做同机位多角度采样，填写模板的 `sweep_review`；不开新固定曝光/分辨率限制。数据检查保留 `data_valid_visual_pending`，最终材质效果仍需 agent 看图，动态效果另需头骨/Actor 运动测试。

烘焙 v2 manifest 记录源 blend、最终 PNG 哈希及编码，纹理审计读取并校验这些关联；旧数据可通过 `--encoding-evidence` 提供真实生成依据。版本标记和数值单测不证明整个材质图的所有上游输入正确，也不替代每角色视觉验收。
