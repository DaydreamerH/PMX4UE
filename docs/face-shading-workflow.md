# 脸部阴影：基线之后执行，材质交付之前收尾

每个角色在材质设计时明确脸部槽及阴影方案。默认角色级 lookdev 中，脸部阴影是必须处理的目标；SDF 是可选实现路线。用户已明确要求 SDF 时，应完成 SDF；换算法或缩减范围须说明差异并取得已有授权支持。不能把源包没有 SDF、配置标 optional 或缺动画当作无限期跳过的理由。

## 执行时点

1. 源数据审核时识别脸部几何、槽、UV、正面和左右方向，记录 SDF 候选或替代方案。
2. 第一组可用材质基线截图完成后，开始脸部专项：探测、生成/适配贴图、绑定和多方向光照测试。与其它独立材质工作可以交错，不等待 IK、物理或动画全部完成。
3. 静态材质交付前关闭此项：真实 SDF 已验证，或有证据的替代脸部阴影方案已验证。无适用脸部才可记 `not_applicable`；存在脸部但不采用 SDF 应写 `alternative` 并说明实际算法与观察。
4. 接入头骨运行时驱动及验证单列。无动作时可完成前三步；`runtime_status=pending_animation` 不阻止静态材质结论，但不能宣称动态 SDF 完成。

若失败，将当前状态记 `blocked/pending`，填写具体 `next_action`、`resume_when` 及阻碍证据。恢复条件应是可判断的条件，如“修正当前 UV 选择后重烘焙”；“后续若需”“有空再做”“等待动画再生成贴图”不算安排。可继续独立工作，但脸部未收尾时材质交付保持未完成，不必等用户再次提出。

## 从真实脸部生成和检查

所有命令从工作台根目录执行，替换真实路径/槽名/方向。使用新输出目录；保留原 mesh、UV、权重与已有材质。这里只列现有工具的真实入口，不假定 `face-sdf` 阶段会生成图。

```powershell
& "<Blender>" --background "<当前导出对应的角色.blend>" --python-exit-code 1 --python tools/blender_face_sdf_probe.py -- --face-slot "<实际脸部槽>" --output "<新产物目录>/face_probe.json"
& "<Blender>" --background "<当前导出对应的角色.blend>" --python-exit-code 1 --python tools/legacy/blender_face_sdf.py -- --character-id "<角色ID>" --face-slot "<实际脸部槽>" --model-faces "+Y" --output-dir "<新的空目录>/SDF" --resolution 512
```

`+Y`、512 只是命令示例。探测器的 `sdf_bake_ready` 只证明找到了面和 UV，不能证明选对脸壳、方向、无 UV 重叠或光照输出有效。agent 要读数据、查看 UV/几何再决定参数；无法满足现有脚本前提时适配脚本，留下可复现的命令和选择依据。

烘焙器仍以最大 UV 连通区域作为候选脸部 mask；这不通用于任意模型，必须确认实际脸壳/鼻口 UV。通用固定椭圆鼻唇高光 G/B 现在默认关闭，只有实际 UV 审阅后才能明确启用兼容模式或实现本角色掩码。R 为方向光扫过时的阴影阈值，A 为应用范围。烘焙角度与 shader 解码、非单调受光检测和旧资产迁移见 [SDF 编码与质量检查](face-sdf-convention.md)，生成前必须阅读。其它编码须同时适配 shader 与数据检查，不直接套入本约定。

先查看 `sweep_quality.json`、`debug_RelitLost.png`、`debug_FrontUnlit.png`。非单调受光损失超阈值时工具保留诊断并停止生成最终图，不默认吞掉问题；核对模型/UV/方向和阴影形状后再决定适配。生成成功后实际打开 `debug_R_ShadowThreshold.png`、`debug_A_FaceMask.png`，及正面/侧面/背光中间 mask；按需要看 G/B。仅看 RGBA 合成图可能误读通道。对完成的 PNG 执行数据检查：

```powershell
& "<Blender>" --background --factory-startup --python-exit-code 1 --python tools/blender_face_sdf_audit.py -- --texture "<实际FaceSDF_RGBA.png>" --output "<新产物目录>/face_sdf_texture_check.json"
```

此检查在 Blender 中按 Non-Color 读取实际图片，记录文件 SHA256、尺寸、RGBA 范围、A>0.5 有效覆盖内的 R 范围和不同阈值下受光比例。全白/全黑的恒定阴影阈值、无有效覆盖都会失败；只在脸部 mask 外有变化也会失败。A 全白或 G/B 常量不单独判失败，关闭高光时这可能合理。无最小像素门槛。结果 `data_valid_visual_pending` 只排除无效数据，不证明 UV 对应或阴影形状正确。

数据检查自动读取同目录 v2 烘焙 manifest，核对纹理哈希并记录 `encoding`；旧图或手绘图必须先审核生成规则，再用 `--encoding` 与 `--encoding-evidence` 记录依据，不能凭灰度外观猜测。编码未知、与 Master 解码读回不一致时交付失败。已有资产不会自动更新，应由执行 agent 在获准工程中新建材质版本后验证。

## 绑定及静态效果验证

将真实贴图声明到脸部槽 `textures.face_sdf`，在新材质版本导入为线性 Masks 数据，检查实际 UV、V 翻转、左右镜像、头部双轴和阈值方向。用 `material-build` 复用已认可 mesh；不要因 SDF 调试重新修改骨架。之后运行 `ue-validate → material-compile`，核对 `input_audit` 的 `face_sdf` 为 `declared` 且实际路径正确，以及 `effective_scalars` 中实际 `FaceMode` 已启用。自定义父图需要对应参数/输入验证适配。

`T_PMX4UE_Neutral_face_sdf` 仅供类型正确的占位采样，不能交付为 SDF。`FaceMode=0` 是功能关闭。不要直接在白色占位图上把开关改成 1；先生成有效数据。不能靠改文件名或清空 debt 把占位状态变成完成。

在直接加载的 Open World 日光地图中，先看默认日光；再为 SDF 方向响应专项检查，对同一个脸部近景和姿态分别设置相对头部的正面、左侧、右侧光照，比较基线与候选。默认沿用场景曝光，只有需要排除自动曝光干扰时才显式固定 EV100，不以反复校准阻塞测试。查看脸颊/鼻梁过渡、左右切换、UV 接缝、全亮/全暗错误，并记录太阳实际参数。相机不动，光向按本模型方向确定；光照名称只是记录，不能替代实际方向检查。替代算法也完成同组检查。贴图变化后重新采集证据。

静态成立后，按 [运行时 SDF](face-sdf-runtime.md) 执行 `face-sdf`，接入头骨驱动并另测转头/低头、Actor 转向和双实例隔离。该阶段修改材质方向输入并创建预览载体，**不会烘焙 SDF 贴图**。

SDF 不能只看正面/左右端点：固定同一近景、姿态和候选，在头部坐标中从左侧到右侧采样至少七个不同角度（例如 -90/-60/-30/0/30/60/90°，相邻不超过45°）。观察转光是否连续、有无半脸直切、鼻口黑斑、突跳或左右翻转；必要时加密问题区间及背光/抬头测试。截图继续使用可见视口和默认 Open World 场景设置，不新增固定曝光或像素尺寸门槛。角度采样不是连续运动的动态验证。

## 交付清单 v2

`templates/delivery.example.json` 升级为 `pmx4ue.delivery.v2`。旧 v1 需补 `face_shading` 决策再检查，不只改 schema。每个条目记录 `slots`、`method`（sdf/alternative/not_applicable）、`status`、选择理由及设计证据、对应 `effects[].id`、静态 `light_tests`、独立的 `runtime_status`。多个脸部槽采用不同算法时分条记录。

- SDF：还需 `texture_asset`、`texture_audit`。后者引用 `evidence` 中 `kind=face_sdf_texture` 的上述数据检查报告。其源图哈希必须仍一致，并匹配当前 `input_audit` 的 `import_source_sha256`；实际槽输入必须为真实声明贴图，通用 Master 必须有启用开关读回。导入源丢失时补回可追溯源数据或适配资产读取，不能用另一张图代替。源文件后来改过还须确认 UE 已在新版本导入；检查器不从 uasset 反解纹理像素，自定义图接线也仍由 agent 核查。
- `light_tests.front/left/right` 填入当前 capture report 中对应 PNG 的 SHA256，并列入被引用 effect 的 `image_sha256`；要求同一报告、相机、候选 case 的三个 Lit 光照设置，不能混用不同旧图。常规 Baseline/候选 A/B 要求继续由 effects 检查。
- SDF 额外填写 `sweep_review`，结构见交付模板：七角度及对应图哈希、实际打开图的 reviewer，并分别写 `nose_cheeks/mouth/uv_seams/transition/nonmonotonicity` 观察。采样图全部属于同一当前报告/相机/候选 case 的 Lit 测试并列入 effect。非单调观察说明损失发生在哪里、修正或接受的具体依据，不以“通过检查”代替画面分析。
- 替代方案：`method=alternative`，引用实现及同组光照证据；缺真实 SDF 导致的 debt 用现有 `alternative_verified` 指向这个已审核效果。理由须基于本模型和目标，不能只是“原包没有图”。
- 无适用脸部：`method=not_applicable`、`slots=[]`，附实际资产审核证据及理由。存在 SDF 启用或缺失记录的槽不能通过此项消失。
- 未完成：`status=pending/blocked` 并给下一步和恢复条件，`delivery-check` 返回 incomplete。其余系统完成不能覆盖此结果。

检查器验证记录的对应关系，不能判断 agent 是否漏认脸部、是否真的看图或算法是否美观。设计表的实际槽分类、画面审阅及用户明确需求仍是 agent 的责任。静态材料 scope 通过不代表动画驱动通过。
