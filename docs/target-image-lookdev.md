# 可选目标图：从外观目标到材质迭代

目标图不是运行前置条件。用户未提供目标图时，不索要图片作为启动门槛；按 PMX、实际 mesh/纹理和文字要求完成材质设计、斜侧光预览与视觉审核。用户后来补图时，从当前已认可版本继续，不重做已通过的无关阶段。

## 从 PMX 素材目录发现并建档

目标图默认随 PMX 素材存放。进入材质设计时，agent 主动查看用户提供的素材根目录及 PMX 所在目录，不要求用户逐张给路径；优先查看 `targets/target/references/参考图/目标图` 等目录，再按实际需要查看散放的候选图。PMX 位于子目录、目标图在其同级目录时，用工单 `source.root` 或用户已提供的素材根目录作为扫描根，不向整个磁盘扩散。目录名和文件名只决定查看顺序，仍需打开原图区分目标、纹理、诊断和算法示意图。

使用离线工具生成候选目录，不运行 UE，也不修改素材。产物保存在当前角色的 `Saved/PMX4UE/<角色>/<版本>/references/`，可跨材质实验复用；原图继续保留在素材目录。命令中的路径都须替换为实际值：

```powershell
python tools/target_image_catalog.py discover --pmx "<素材根>/model.pmx" --source-root "<素材根>" --output "<产物目录>/references/catalog-v1.json"
```

已有导出 manifest 时附 `--manifest "<产物目录>/blender_manifest.json"`，标记实际引用纹理，辅助避免混淆；尚未导出则纹理引用记为 unknown，不阻碍早期目标分析。用户另行提供素材目录外的图片时可重复使用 `--image "<实际图路径>"`。扫描支持常见图片扩展名；扩展名不保证图像可读取，打开失败要记录限制，不填写 images_opened。

工具只生成 `kind=candidate`、内容 SHA256、稳定 image ID、实际路径/素材相对路径和发现线索，不猜图像语义，不宣称已看图。相同内容的多路径合并为一张；不因文件名包含丝袜/脸就自动绑定材质。优先看相关候选，无需为了建档打开全部源纹理。

看图后在 JSON 中编辑对应 `images[]` 条目：

- `kind` 区分 `target/source_texture/diagnostic/algorithm_reference/irrelevant`；无法判定时保持 candidate 并写明疑点。目标候选在用户提供的素材包中、且与当前需求一致时可由 agent 自行采用，不逐张要求用户批准；冲突或模型不对应时先分析再处理。
- `review.images_opened=true`、真实 reviewer 和 `selection_reason` 记录采用/排除依据。只有实际打开原图后才能记为已查看。查询只返回已看图、有区域记录的 target。
- 在 `regions[]` 为每个重要区域建立 ID、可见特征、优先级、适用任务、镜头/光照线索和局限。一张图可以同时记录丝袜、衣料、脸部和全局信息；同一区域可有多个标签。标签建议为 `stocking/cloth/face/eye/hair/global/outline/rim`，可按模型扩展；特征可用 `edge_thickness/specular/shadow/color/silhouette` 等，**描述观察，不从观感推定 shader 算法**。
- `bbox_normalized` 可填写原图左上角起算的 `[left, top, right, bottom]`（0–1）。不确定位置时留 null，写清部位与文字定位；不要套用示例坐标。原图与哈希始终保留；可另存局部裁剪作辅助，但不覆盖原图，也不以插值放大补细节。
- `material_slots` 仅填已核实的当前槽，无证据时留空。目录是图像索引，不是 UE 绑定证明；选定 mesh/槽改变后重新核对这项映射。

区域字段参考 `templates/target-image-region.example.json`；其中的占位词须替换为实际观察，不把示例直接视为审核完成。先建可用档案，后续新发现的局部信息增补到同张图的 regions，不重复寻找原图。

## 渲染前按需要快速定位

丝袜、布料、脸部或全局任务开始时查询对应标签；可用 `--text` 在特征和观察中进一步定位，多次 `--tag` 表示同一区域同时含这些标签：

```powershell
python tools/target_image_catalog.py query --catalog "<产物目录>/references/catalog-v1.json" --tag stocking --text edge_thickness
python tools/target_image_catalog.py query --catalog "<产物目录>/references/catalog-v1.json" --tag cloth
python tools/target_image_catalog.py query --catalog "<产物目录>/references/catalog-v1.json" --tag face
python tools/target_image_catalog.py query --catalog "<产物目录>/references/catalog-v1.json" --tag global
```

结果包含原图可用路径、内容哈希、image/region ID、区域框和观察，按优先级排序。agent 打开所选原图或辅助局部图，结合档案快速确定本轮效果与预览机位；旧观察不能代替对新渲染图的实际看图。有候选未审阅而查询无结果，不等于没有目标图；回到发现清单查看相关候选，必要时补全标签。

在 material-design/material-review 中引用 `catalog 路径与哈希 + image ID + region ID`，再引用本轮真实 capture；交给材质专项或视觉审阅智能体时只传相关条目、原图路径与必要素材证据。全身任务检索 global，局部任务检索对应材质族，避免把一张全身图当成所有局部细节的依据。源图未展示的特征仍按 mesh/纹理和文字要求处理，不必为每个效果强找图片。

素材移动、新增图片或重新建档时生成新版本，使用 `discover --previous "<旧目录档案>" --output "<新的目录档案>"`。工具仅对同 PMX、同图像内容保留语义记录；内容变更后新条目重新审阅，并列出消失/变化的旧 image ID。路径迁移但内容不变可继续使用相同 ID；PMX 变更则建立新模型档案。query 会核对 PMX 和原图指纹，失效图不返回为可用目标；当前比较需重新引用新哈希。

如果最终没有适用目标图，记录扫描范围与原因，继续正常流程；不留下假的目标图对照。目录中的纹理、诊断图与未采用候选不自动进入 delivery 的目标来源。

## 有图时先确定图的角色

实际打开原图，记录文件路径与 SHA256，并区分：**期望复现的目标图**、当前 UE 结果或故障截图、算法文章示意图。只有第一类进入目标对照；其它图片可用于诊断或启发，不能擅自当成用户的最终美术目标。多张目标图要记录区域、视角和优先级；互相矛盾时指出冲突，不能挑对自己实现最有利的一张代替用户意图。

从图中描述可观察量，而非猜测算法：例如脸颊阴影形状、发束高光宽度、虹膜层次、袜边颜色/厚度观感、织物反射、描边宽度和边缘光范围。每项对应本次角色实际存在的表面与材质槽，在 `material-design.md` 写明目标图区域、可见特征、优先级、当前资产证据、候选实现与不确定项。图中未展示的背面、动画稳定性、透射、内部几何和 shader 公式均不得凭空推定。

## 迭代顺序

1. 先按当前 mesh 正面校准正面斜侧光，在该光下获得清晰的 Lit 全身及相关局部图；目标图不能代替对 UE 材质的实际截图。确认基础外观正常之后再转光，遵守 `agent-material-workflow.md`。
2. 对每个目标区域，尽量匹配相机视角、距离、姿态、可见部位与光照关系。无法匹配时记录差异及它可能怎样影响判断；不为“对齐”偷偷改曝光、源贴图、几何或已认可的场景基线。比较的是可观察的材质行为，不要求像素级一致。
3. 在 `material-review.md` 逐项并排引用目标图与当前渲染图的路径/哈希，写出**具体差距**、优先级、原因假设、只改变一个主要因素的实验和结果。颜色大体一致不表示脸部阴影、眼睛层次、发束高光、丝袜边缘、描边已完成。若发现图与当前资产结构不符，先检查实际几何/UV/遮罩，再决定替代算法或记录限制，不能猜测透射/多层结构。
4. 调整后用相同机位、主光与曝光策略重拍，重新看原尺寸图，再决定保留、继续迭代或说明经用户接受的偏离。斜侧主光确认正常后，再用另一光向检查是否只对单角度成立。材质或截图条件变化会使旧比较失效。

目标图可具有不同背景、色调映射和镜头，因此不要用未校准的像素差、颜色平均值或自动相似度分数代替审美判断。`delivery-check` 只在提供了 `target_image_review` 时核对文件/截图指纹与条目完整性，不判断相似度；无图时省略该字段即可正常交付。

有目标图并进入交付时，可在 `delivery.json` 顶层填写：

```json
"target_image_review": {
  "status": "reviewed",
  "images_opened": true,
  "reviewer": "REPLACE_WITH_ACTUAL_REVIEWER",
  "sources": [{"path": "D:/References/target.png", "sha256": "REPLACE_WITH_REAL_SHA256"}],
  "comparisons": [{
    "source_sha256": "REPLACE_WITH_REAL_SHA256",
    "region": "实际区域",
    "feature": "可观察的材质特征",
    "result_image_sha256": "REPLACE_WITH_CAPTURE_SHA256",
    "conditions": "视角、姿态、光照与曝光的可比性或差异",
    "observation": "具体相符处及差距",
    "disposition": "matched",
    "next_action": ""
  }]
}
```

`disposition` 允许 `matched`、`iterate`、`accepted_limitation`。`iterate` 需写 `next_action` 且交付保持未完成；`accepted_limitation` 需写 `limitation_reason` 与用户对该范围的 `scope_approval`，不能由 agent 自行宣称批准。每张**实际采用并写入 sources 的目标图**至少有一条对照，结果须引用当前 capture 报告中的 Lit 图。sources 从本轮采用的目录条目解析为真实 path/sha256；目录的候选、纹理、排除图不计入。image/region ID 用于设计与审阅快速定位，不替代现有 delivery 字段；可把目录作为额外 evidence 保存。缺目标图时不要复制上述示例或填假的占位路径。
