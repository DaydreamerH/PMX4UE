# 头发与刘海装配记录

按 `docs/hair-rendering-standard.md` 填当前模型实值。此表是 agent 设计/接入记录，不是 runner 可执行配置；没有装配工具也不得将公式 helper 当完整实现。

- 工作单、mesh/材质版本与指纹、运行时提供方、源资产保护范围：
- 可选目标图 catalog/image/region ID；无图时依据：
- 球心与 Head 枢轴的区别、绑定姿态 Forward/Left/Up 校准和左右身份：

## 主体计算

| 区域/真实槽 | 球面漫反射范围与混合 | 高光算法/有据替代 | Head 或球心高度原点、宽度/视线/侧向弧度 | 发束遮罩或显式亮度近似及 UV | 完整下游门控与实际读回 |
|---|---|---|---|---|---|
| 刘海 | | | | | pending |
| 头盖/后发 | | | | | pending |
| 长发/物理发束（如有） | | | | | pending |

- 参考规范与实际图差异（例如 helper 无侧向弧度），为何可接受/如何适配：
- `preserve` 若被选用，认可原高光的证据；不能只因默认而选：

## 实际层路由

刘海本体保留 Opaque/Masked；补绘眉眼，不要求删除原刘海像素。不存在的层有据 N/A。

| 层角色 | 实际组件/资产 | 允许的 slots/各 LOD sections | 材质、主/深度/CustomDepth 与 Stencil 设置 | 共享姿态/bounds/排序 | 保存后重载读回 |
|---|---|---|---|---|---|
| 主头发 | | | | | pending |
| FringeDepth | | | | | pending |
| BrowPeek | | | | | pending |
| FringeShadow | | | | | pending |
| EyePeek | | | | | pending |

- 代理真实裁切与源 Alpha/AlphaScale/SourceClip；不是填一张全白代理遮罩：
- 本眼 R/G mask 来源、左右符号；眼白 frontmost 排除前方虹膜/眼睑证据：
- 眼层完整父图和实例输入继承读回，原高光层是否保留；二值/连续覆盖策略：
- Pixel/Scene/CustomDepth 同空间与单位、真实间距、前景可见性、正面渐隐：
- 五角度几何遮挡、距离场编码/UV、额头接收覆盖与仰角/姿态适用范围：
- Head/Forward/Left/Up/球心/Valid 的真实输入和 MID，缺骨关闭/解绑恢复；不能只填共享驱动名字：

## 实际证据与交接

| 专项 | 配置/图/组件及编译报告 | 同条件局部 Lit 关/开原图 | 观察/保留或退回 | 当前状态与 next_action |
|---|---|---|---|---|
| 球形漫反射 | | | | pending |
| 刘海与后发高光 | | | | pending |
| 额前投影 | | | | pending |
| 眉睫与一致眼层补绘 | | | | pending |

- 与临时无刘海诊断的眼形/叠白/灰圈比较；正式组合不得隐藏刘海：
- 主光初评后俯仰/转光/斜侧，以及前景遮挡结果；异常才扩大采图：
- 最终 BP/组件、材质覆盖、source hashes、重载回执、delivery.effects ID：
- 静止关/开与最终组合性能报告；t.MaxFPS=200 回读、Frame/GPU P95/P99 和预算：
- 连续运动、表情/眨眼、发束变形、LOD、多实例/模板冲突已验或待验；static_lookdev 不等于 game_ready：
