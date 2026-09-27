# 材质：agent 判断，脚本构建

开始本领域工作时还需完整阅读 [材质迭代与交付](../../../docs/material-iteration-and-delivery.md)。按版本/API 风险选用 `material-preflight`；第一轮基线尽早截图，材质实验使用 `material-build` 复用已认可 mesh，最终用 `delivery-check` 检查明确版本组合和证据。缺资源关闭功能只算排错，必须跟进 `material_debt` 与设计表目标。不要通过删掉源输入、缩减交付范围或勾选审核标记制造完成。

默认交付目标是角色级 lookdev，不是通用 Master 的基础贴色。材质设计前完整阅读 [material-families.md](../../../docs/material-families.md)，根据实际模型填写 `templates/material-design.md`：逐类确定脸部、头发/刘海、眼睛各层、袜类、不同织物/硬表面和轮廓效果的计算、父图/Pass、输入与验收。颜色正确只算基线；不按 Master 个数考核，但不同行为必须真正实现。文章/案例用作方法参考，不能假定其轴、UV、Pass 或参数适合新模型。

运行 `material-draft`，由 Blender manifest 的真实材质槽生成未绑定草稿。检查源贴图图像、PMX 槽参数、UV、透明类型和参考效果，然后填写 material_map。文件名只提供候选，不能据 `_N` 等后缀自动绑定法线或打包通道。

`presets/materials.v1.json` 提供可编辑的起点；`mmd2ue_core.normalize_material_map` 是规范化接口。按需读取该函数和 `validate_material_map` 的字段约束，不另造不被构建器消费的配置字段。`material-check` 执行纯 Python 的槽覆盖与审核校验；再设置 `pmx4ue.material_reviewed=true`，执行 `ue-build`。此阶段导入选定的 FBX 与贴图，创建材质，不配置或保存用户场景。

`parent: stocking/cloth` 已接入专用图构建；`parent_assets` 可注册 agent 编写并保存的其它专用父图。未知/冲突父路由、专用图缺输入会失败，不回退 Master。专用图用自己的参数 profile，不拷贝通用图的全部开关；真实能力和配置语法见 material-families。轮廓/后处理/刘海额外绘制层不是槽父材质替换，需要单独接入和验证。

新变体必须使用空命名空间。构建失败产生部分资产时，先检查日志，选择新版本或得到明确范围后清理，不让重复导入覆盖已有角色。

`ue-validate` 检查槽绑定、图连接、纹理配置。报告中 `compile_check_required` 必须另外用插件 `PMX4UEAgentMCPTools.inspect_material_compile` 检查；图连通并不证明 shader 编译成功。最终还需 Lit/Unlit/WorldNormal 和不同光照角度的视觉检查。

进入视觉阶段前完整阅读 [agent-material-workflow.md](../../../docs/agent-material-workflow.md)。使用审核的 `material_preview.example.json` 和 `material-preview` 阶段：自有新编辑器、隔离地图、相同视角/光照的材质 A/B、异步截图完成校验。不要调用旧 current-level setup，也不要因为会话缺少截图 MCP 工具而停止；插件公开方法可直接通过 UE Python 使用。无法出图则记录阻碍，不能以编译结果签收。

逐项处理未分类贴图，记录纹理→槽→UV/通道证据；填写 `templates/material-review.md`，实际打开截图后才判断视觉。用户要求的效果即使属于可选功能，也要做隔离对照或明确列出缺口。没有动作不妨碍这些静态测试。

## 按需效果

Face SDF、轮廓、丝袜/布料专用材质、头发高光按模型与目标选择，并非每个 PMX 都必须具备；但“可选”不能成为存在相关材质却不分析、不实现的理由。相关工具已复制到 `tools/legacy`，根据材质设计表选择、改写和验证：

- `tools/blender_face_sdf_probe.py`：按真实脸部槽名探测 UV/朝向。
- `tools/legacy/blender_face_sdf.py`：显式传入 face slot 和 model-faces，独立后台场景烘焙。
- `ue_feature_outline.py` / `ue_feature_depth_rim.py`：会影响指定场景实例，先确认用户允许的测试场景，不能作为基础导入的隐藏副作用。
- `ue_feature_cloth.py` / `ue_feature_stocking.py`：先判断真实槽、通道、法线与纤维方向，再构建；缺资源优先考虑基于本模型生成/适配，暂退基础材质仅算 baseline，不算完成。脚本中旧默认颜色和 UV 不是当前角色的审核结论。

法线发黑先做零模拟对照，再分别检查拓扑绕序、变换 handedness、法线/切线与材质，不能直接反转所有法线。受物理影响只在模拟路径出现时，先查模拟→骨骼变换，不重写原本正常 mesh。

## 动画中的面部 SDF

材质编译通过不代表面部朝向随动画更新。启用 Face SDF 的游戏角色还应按 `docs/face-sdf-runtime.md` 检查头骨驱动、参考姿态轴校准、世界/模型空间契约和每实例参数隔离。审核 `templates/face_sdf.example.json` 的角色副本，设置工单 `pmx4ue.face_sdf_profile`，执行 `face-sdf` 阶段，生成独立材质与预览 BP。插件含 `PMX4UEFaceSDFComponent`，MMD2UE 使用现有 `MMDFaceSDFComponent` 适配，不安装重复插件。不要把 Actor 朝向当头骨朝向，或将已是世界空间的轴再次 Local→World。验收应在拥有驱动组件的角色实例进行，不以普通 ABP 预览代替；新角色必须重新确认双轴与视觉效果。
