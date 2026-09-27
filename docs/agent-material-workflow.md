# Agent 材质闭环：证据、隔离对照、截图、验收

本流程不要求动画。没有源动画会阻止动态重定向、移动物理、动态 SDF 验收，不会阻止材质的静态视觉工作。脚本负责重复操作和证据完整性，agent 必须实际打开图片判断效果。

进入构建前先按 [材质族设计](material-families.md) 完成 `material-design.md`：区分不同表面的计算与渲染层，建立目标效果和实际工具能力的对应关系。本文负责预览和验收闭环，不能代替眼睛/头发/丝袜等专用实现。最终不要把一个通用 Master 的基础贴色当作角色级材质完成。

执行顺序及新增工具见 [材质迭代与交付](material-iteration-and-delivery.md)：先取得最小基线画面，再做局部效果；新环境先小探测，纯材质迭代复用网格，实际输入和降级项进入交接检查。不要把第一轮截图推迟到所有角色系统完成之后。

## 1. 从源资料建立可追溯关系

读取 source audit、Blender manifest、PMX 材质参数和实际贴图。逐项建立：纹理文件 → 引用材质槽 → UV/遮罩通道 → 材质用途 → 采用/不用的理由。不能让 `Socks.png` 之类未分类贴图没有结论地流入最终交付；名字只提供候选，需检查像素、alpha、UV 覆盖及对应身体区域。

为本角色复制 `templates/material-review.md`。明确区分用户要求、源材质已有特征、agent 提议的可选风格。用户已要求的丝袜厚度/高光、描边或边缘光，不能再以“按需功能”为理由跳过；应创建隔离变体或明确缺少的能力/证据。反之，没有依据时不自动加黑丝、额外描边或全场景后处理。

白丝“厚度”可能指边缘透明度、遮罩过渡或实际几何轮廓：先看源图和参考，不能把增加模型厚度当默认修复。保留原网格/权重；每次仅对一个效果做对照。

## 2. 构建和 API 故障定位

执行 `material-check → ue-build → ue-validate → material-compile`。图连通、shader 编译和视觉表现分别记录。

- 连接失败应记录目标节点类、请求输入名、实际输入名和引擎版本。`ue_context.connect` 现在提供这些诊断。不要假定每个单输入节点都叫 `Input`；以安装版本源码/API 为准。
- 需要替换为等价节点时，记录表达式及其定义域，例如平方根换幂运算还须保留输入的非负约束。不要为消除错误改变计算语义。
- 可选 TextureSampleParameter2D 分支也必须有实际默认纹理。构建器现在拒绝空纹理或关键属性写入失败；占位纹理应按 Color/Normal/Masks 的采样类型选取，再通过实际 shader 编译确认，不能只“塞一张白图”。
- 当前通用主材质构建脚本没有创建 SquareRoot 节点。其它工程的这个节点修复不能因此被宣称已合入或普遍适用。

## 3. 独立预览，不操作用户当前关卡

复制 `templates/material_preview.example.json` 到角色配置目录，agent 根据模型调整：

- `mesh` 为已保存的本次角色网格；`level` 必须是工单 namespace 下全新的 `Preview/...` 地图。
- 相机朝向、距离、高度按实际模型确认。默认 front/side 只是候选，不是由文件名推断的正面。可加腿部近景；原生桥当前限制距离 100–1200cm、高度 -100–200cm、FOV 20–90°，超出先适配而不是悄悄截断。
- 灯光至少选择有辨识力的两个角度，曝光固定；示例使用扩展亮度范围的 EV100。如果工程不支持该设置，脚本会停止，应适配曝光接口，不擅自改全局画质。
- 三种模式均保留：Lit、Unlit、WorldNormal。每个案例使用相同相机、光照、模式组合，便于 A/B。
- 第一个 case 严格为 `{"name":"Baseline","slots":[]}`。其它 case 可以用组件级材质替换或临时标量参数。未知参数报错，不能静默忽略。

单槽实验例（将索引、路径、参数替换为实际已审核值）：

```json
{
  "name": "StockingHighlight",
  "slots": [{"index": 3, "material": "/Game/PMX4UE/Character/v1/Materials/MI_Stocking_Test", "scalars": {"Roughness": 0.6}}]
}
```

实验材质先在独立路径构建/保存。不能修改共用父材质然后将 Baseline 当作“修改前”。若比较高光和厚度，两者拆成两个 case；是否组合由单项结论决定。

描边 case 可加 `"outline":"/Game/.../M_Outline_Test"`，表示全槽覆盖描边材质；头发/脸部不同策略需扩展 profile 和脚本，当前不隐式推断。边缘光 case 可加 `"depth_rim":"/Game/.../M_DepthRim_Test"`，要求工程已支持 CustomDepth+Stencil；工具不会修改项目设置。两项都只影响本次预览实例和隔离地图的临时状态。它们是已有材质的应用入口，**不是**自动创建适合任意模型的描边/边缘光图。

审核后设 `reviewed=true`，工作单增加/更新：

```json
{
  "material_preview_profile": "<角色配置目录的绝对路径>/material_preview.json",
  "material_preview_run": "v1"
}
```

这些字段放在工作单的 `pmx4ue` 对象内。运行：

```powershell
python pmx4ue.py run --config "<工作单路径>" --stage material-preview
python pmx4ue.py run --config "<工作单路径>" --stage material-preview --execute
```

脚本启动自己持有的新完整编辑器进程，不连接用户当前编辑器；启动标记、目标工程及初始地图三重检查后才创建新地图。不调用旧的按类型清理角色/灯光，不调用 SaveDirtyPackages，不保存原网格/材质。只保存第一组未修改基线预览地图，后续 A/B 覆盖不落到共享资产。

材质变体、头发描边分槽、动态 SDF 等特殊需求由 agent 根据源码定向扩展；不要因工具只覆盖默认效果就把需求默默删掉。

## 4. 截图落盘，而不止“已发出命令”

`ue_material_preview.py` 直接调用插件公开的 UE Python 方法，不依赖聊天会话有没有同名 MCP 截图工具。旧 `ue_build_character.py --mode preview/full` 已禁用，先 build 再用新阶段；旧 `_destroy_previous` 也不再删除当前地图对象。

采集会重新检查基线和变体的材质父链编译，预热后逐张拍摄。截图接口是异步调度：脚本等待实际 PNG 完整、CRC 和尺寸正确，超过 60 秒失败。原生截图保留在工程 Saved 的 provider 捕获目录，另复制到本次产物目录，文件名包含唯一运行标记，避免读到旧图。

产物位于 `<artifact_dir>/material_previews/<material_preview_run>/`：

- `material_preview.json`：完整配置、引擎/provider、相机、光照、视图模式、图片路径/哈希、编译结果。
- `captures_<运行标记>/`：可供 agent 打开的实际图片。
- 基线地图位于 profile 指定的 Content 路径，可在编辑器内复查。

运行器检查图片完整性、矩阵覆盖、图片及项目资产哈希。状态查询也追踪这些指纹。引擎/插件外部依赖只列路径，不声称完整二进制指纹覆盖，交接需保留版本。截图分辨率不是性能测试 viewport 分辨率。

**`captured_visual_pending` 仍不代表画面正确**：有效 PNG 也可能黑屏、取景错误、角色太小或未充分加载贴图。agent 必须打开图检查；需要时增加预热、纠正相机或补近景，并使用新运行名和新地图路径重跑，不覆盖失败证据。图片产物不全、接口缺失或离屏渲染失败时记 `capture_failed/blocked`，不能退回“编译通过所以完成”。无需启动另一个空白项目。

## 5. 实际看图和交付

填写 material-review，每个效果至少引用基线与变体的相同视角/光照截图，记录观察、选择、缺陷和下一步。需看正面/侧面/局部和改变光照后的稳定性，不只挑一张好看的图。无法读取图像的 agent 将视觉审核交接给有图像能力的 agent/用户，保留 pending，不自动签字。

从截图得到的仅是当前模型的静态外观结论；动态头骨 SDF、透明排序随动作变化、物理碰撞及游戏性能仍分别走各自验收流程。材质变更后旧截图立即过期，需重新采集。
