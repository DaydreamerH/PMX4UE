# 材质：agent 判断，脚本构建

运行 `material-draft`，由 Blender manifest 的真实材质槽生成未绑定草稿。检查源贴图图像、PMX 槽参数、UV、透明类型和参考效果，然后填写 material_map。文件名只提供候选，不能据 `_N` 等后缀自动绑定法线或打包通道。

`presets/materials.v1.json` 提供可编辑的起点；`mmd2ue_core.normalize_material_map` 是规范化接口。按需读取该函数和 `validate_material_map` 的字段约束，不另造不被构建器消费的配置字段。`material-check` 执行纯 Python 的槽覆盖与审核校验；再设置 `pmx4ue.material_reviewed=true`，执行 `ue-build`。此阶段导入选定的 FBX 与贴图，创建材质，不配置或保存用户场景。

新变体必须使用空命名空间。构建失败产生部分资产时，先检查日志，选择新版本或得到明确范围后清理，不让重复导入覆盖已有角色。

`ue-validate` 检查槽绑定、图连接、纹理配置。报告中 `compile_check_required` 必须另外用插件 `PMX4UEAgentMCPTools.inspect_material_compile` 检查；图连通并不证明 shader 编译成功。最终还需 Lit/Unlit/WorldNormal 和不同光照角度的视觉检查。

## 按需效果

Face SDF、轮廓、丝袜/布料专用材质、头发高光不是每个 PMX 的必选功能。相关工具已复制到 `tools/legacy`；agent 审核后可单独运行、改写或接入 runner：

- `tools/blender_face_sdf_probe.py`：按真实脸部槽名探测 UV/朝向。
- `tools/legacy/blender_face_sdf.py`：显式传入 face slot 和 model-faces，独立后台场景烘焙。
- `ue_feature_outline.py` / `ue_feature_depth_rim.py`：会影响指定场景实例，先确认用户允许的测试场景，不能作为基础导入的隐藏副作用。
- `ue_feature_cloth.py` / `ue_feature_stocking.py`：先判断模型是否有合适 mask，再构建；缺资源时退回基础材质并记录差距。

法线发黑先做零模拟对照，再分别检查拓扑绕序、变换 handedness、法线/切线与材质，不能直接反转所有法线。受物理影响只在模拟路径出现时，先查模拟→骨骼变换，不重写原本正常 mesh。

## 动画中的面部 SDF

材质编译通过不代表面部朝向随动画更新。启用 Face SDF 的游戏角色还应按 `docs/face-sdf-runtime.md` 检查头骨驱动、参考姿态轴校准、世界/模型空间契约和每实例参数隔离。审核 `templates/face_sdf.example.json` 的角色副本，设置工单 `pmx4ue.face_sdf_profile`，执行 `face-sdf` 阶段，生成独立材质与预览 BP。插件含 `PMX4UEFaceSDFComponent`，MMD2UE 使用现有 `MMDFaceSDFComponent` 适配，不安装重复插件。不要把 Actor 朝向当头骨朝向，或将已是世界空间的轴再次 Local→World。验收应在拥有驱动组件的角色实例进行，不以普通 ABP 预览代替；新角色必须重新确认双轴与视觉效果。
