# 材质迭代与交付：小实验、实际输入、明确版本

与 [材质族设计](material-families.md)、[视觉闭环](agent-material-workflow.md) 配合使用。本页规定如何缩短实验、避免输入串槽及交接遗漏，不规定每个角色必须使用相同算法。新增入口尚未在 UE 实测，验证边界见 `VERIFICATION.md`。

## 1. 尽早得到第一组可信画面

先分析模型和参考、写材质设计表，再做最小基线：`material-check → ue-build → ue-validate → material-compile → material-preview`。第一组隔离预览至少确认取景、基础色、透明层和法线；不要等重定向、物理、所有高级材质完成才发现无法截图。没有动画不阻止静态材质工作。

基线之后按差距安排局部实验，例如白丝边缘/高光、头发高光方向、眼睛分层、脸部阴影、轮廓距离变化。每轮记录：观察 → 假设 → 唯一主要变量 → 同条件对照 → 保留/放弃理由。证据支持不同算法时，agent 应改写图或脚本，不局限于调旧参数。

截图失败时先做最小相机/灯光/单 case 诊断，保留日志；按照视觉闭环排查新编辑器、桥接口、渲染与异步输出。无画面可继续独立的数据审计或工具适配，但材质必须保持 `visual_pending/blocked`。不能把“等用户看”作为默认结束方式。

## 2. 每槽实际输入，不借用其它槽的默认纹理

构建器对父图支持的标准纹理参数逐项显式赋值并读回；未声明资源使用新版本目录内、符合 Color/Normal/Masks 类型的中性纹理，不再挑选其它槽的贴图。`ue-validate` 的 `slot_audit[].input_audit` 记录 declared/generated_neutral、期望与实际完整路径。

通用 Master 缺 Normal、RMO、头发高光遮罩、ramp、Face SDF 时，相应依赖开关归零；被请求但因此关闭的效果记入 `material_debt`。**停止错误采样是排错成功，不是效果实现成功。** Agent 要选择审核后的真实输入、针对模型生成辅助输入、替代算法，或获得明确的范围缩减同意。预设本就关闭的效果不会自动形成 debt，因此材质设计表仍须覆盖参考需求，不能只处理脚本列出的 debt。

专用/自定义父图使用其自身接口和输入要求；脚本不会猜测自定义图的依赖开关。相同纹理键同时声明为 Color 与 Normal/Masks 会在构建前报错，需要真正分开的采样资源或适配，而不是修改共用资产去迁就一个槽。

当前标准绑定适配器只消费 `TEXTURE_PARAMETER_NAMES` 中的角色。`sphere_map/opacity_mask` 等源信息不等于通用图已经支持它；非空、未支持输入会报错，不再静默丢弃。Agent 应保留源证据，完成专用图和绑定/验证适配，或在设计表说明不采用的依据；不能仅删除配置以绕过错误。

## 3. 新版本环境先做小规模兼容性探测

首次使用新的 UE 版本或修改采样/节点适配时，先执行：

```powershell
python pmx4ue.py run --config "<工单>" --stage material-preflight
python pmx4ue.py run --config "<工单>" --stage material-preflight --execute
```

只在本版本 `Preflight/` 下生成中性纹理及一个探测材质，检查类型采样器、基础连接与实际 shader 编译。报告是 `material_preflight.json`；`probe_passed_character_pending` **不覆盖完整角色图、FBX、插件构建或视觉验收**。角色构建允许同版本已有的 Preflight 子目录，不允许其它已有资产。

运行记录包含源码指纹和报告中的引擎版本。Agent 核对版本与工具指纹后可引用原探测证据；没有自动跨版本兼容缓存。发生新故障时先定位具体失败接口并缩小探测，不反复完整导入模型。UBT Trace 沙箱问题仍按环境规程处理，不把换 `-Log` 当作修复。

## 4. 只改材质时复用已认可网格和纹理

复制工单为新的材质实验版本，使用新的 `paths.ue_root`、`paths.artifact_dir`、材质配置及报告目录。将已认可网格的 `blender_manifest.json` 复制到新产物目录，并保留源构建 run 的证据；不得伪造不同槽顺序的 manifest。不要重新运行 export 或 ue-build。

在工单的 `pmx4ue` 内设置（示例路径须替换）：

```json
{
  "material_source_mesh": "/Game/PMX4UE/Character/base/Mesh/SK_Character",
  "material_texture_assets": {
    "hair": "/Game/PMX4UE/Character/base/Textures/hair"
  }
}
```

纹理键必须与材质表声明一致（现有导入器通常使用不含扩展名的小写 stem，如 `hair`）；复用的是已保存的 Texture2D，不重配其导入设置。所有声明纹理都复用时无需再复制 textures 目录；新生成的辅助纹理仍按新版本导入。实际类型不匹配须新建适配资源，不改旧纹理。

```powershell
python pmx4ue.py run --config "<材质实验工单>" --stage material-build
python pmx4ue.py run --config "<材质实验工单>" --stage material-build --execute
```

此入口核对网格槽数量/身份顺序，生成新父图/实例，**不重新导入 FBX，不给旧 mesh 写入材质**。构建报告给出 `component_overrides`（index/slot/material）；运行器保留源 mesh/显式复用纹理的磁盘哈希并检查未改动。随后执行同工单的 `ue-validate → material-compile`。

预览 profile 的 `mesh` 使用精确的 `material_source_mesh`；Baseline 保持原网格材质，候选 case 从构建报告选取需要比较的组件级覆盖。新预览地图仍在本版本 namespace 下。`ue-validate` 在此模式检查新实例与输入，而不是声称旧 mesh 已切换新材质；报告标为 `unassigned_component_overrides`。最终采用哪些覆盖写入交接清单，用户授权后再接入正式角色组件。

## 5. 按资产组合与效果交付，不按“最新文件夹”交付

从 `templates/delivery.example.json` 建立 `delivery.json`，工单 `pmx4ue.delivery_profile` 指向其绝对路径。模板有占位符和 pending，不能直接视为完成。

- `assets` 明确选择 mesh/skeleton/材质/IK/PA/ABP/动画实际路径、文件 SHA256、证据引用和兼容性说明。材质可来自新版本、骨架和物理来自旧版，但必须说明组合关系。
- `evidence` 用绝对路径和 SHA256 引用原始构建 run、新材质构建 run、当前 `ue_validation.json`、采集报告及审阅文档。保留基础 mesh 的导入警告，不让后续材质成功盖掉 `zero length normal` 等风险。
- `effects` 覆盖验证报告中的全部槽，并对应材质设计表的目标，不只列成功的特征。实际看图后填写实现、观察、reviewer、images_opened 和截图哈希。默认要求同一报告、视角、光照、模式的 Baseline/候选对照。无需 A/B 的项目设 comparison_required=false 并填写 comparison_reason；不适用项目须证据及理由。
- `dispositions` 处理每项自动降级/导入风险。`accepted_limitation` 要有原因、范围批准及证据；`alternative_verified` 引用已审阅替代效果。不能将仍关闭的功能写成已修复。

```powershell
python pmx4ue.py run --config "<交付工单>" --stage delivery-check --execute
```

`delivery_check.json` 检查文件/资产/图片指纹、原始 run 输入输出、实际输入审计、槽覆盖、效果证据和未处理事项。失败保留报告；修改清单后使用新的交付工单/产物目录复核，不覆盖旧结论。

成功仅为 `evidence_complete_needs_human_judgment`，`visual_accepted` 始终为 false。它不能证实 agent 真看过图、所有参考需求都已被列出、或引擎中任意版本组合真兼容。材质 scope 不能代替动画 SDF、物理、玩法或性能验收；这些证据与未完成项在 handoff 分列。整体交付不能缩成 materials scope 后宣称全部通过。
