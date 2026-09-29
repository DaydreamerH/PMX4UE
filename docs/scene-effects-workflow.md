# 描边、边缘光：选择 → 构建 → 场景接入 → 实际对照

两项都要审阅，不等于所有模型都强制开启。agent 根据真实 mesh/法线、槽、透明层、源风格和可选目标图选择算法；没有参考图不阻止试验。不能因为是“与场景有关的可选功能”就沉默跳过。没有动画也能完成静态对照。

## 旧流程的缺口

初始化 `features={}`；主运行器只创建基础/专用槽材质，没有描边/边缘光构建阶段；预览默认只有 Baseline，只有 case 显式带 outline/depth_rim 才会挂载。即使旧脚本生成了描边材质，也不代表场景角色在用它。之前 depth-rim 还要求全局 stencil 设置，agent 容易因不愿修改场景而放弃。现在用隔离预览解决，不改变用户当前关卡。

## 执行顺序

1. 基础材质完成 compile 和首组日光基线后，在 material-design 分别填写 outline/rim 的候选算法、真实输入、适用性及预期效果。描边检查法线、距离缩放、面部/透明层；边缘光区分材质光照响应、Fresnel 与屏幕空间深度边缘，不能把三者当同一算法。
2. 使用现有逆壳描边/四邻域 CustomDepth 边缘候选时，在工作单显式配置 `features.outline.mode="enabled"` / `features.depth_rim.mode="enabled"`，按实际模型填写参数。主命令 `python pmx4ue.py run --config <工作单> --stage scene-effects-build --execute` 只创建选中资产，不运行旧全套 feature 入口，不修改用户场景。输出 `scene_effects_build.json` 和各自 build report，包含准确材质路径。
3. 父图/实例已存在时拒绝覆盖；进一步修改使用新的材质变体命名空间。现有构建器只提供候选，不适配时 agent 新写图并记录，不关闭必要检查假装完成。旧 mode=inverse_hull/post_process 配置迁移为 enabled 前必须复核算法/参数，不自动迁移为启用。
4. 从构建报告取路径，在新的 material-preview 版本加入独立 case；默认沿用日光场景曝光，固定曝光和独立环境校准不是前置条件：

```json
[
  {"name":"Baseline","slots":[]},
  {"name":"OutlineOnly","slots":[],"outline":"/Game/实际路径/MI_Outline"},
  {"name":"RimOnly","slots":[],"depth_rim":"/Game/实际路径/MI_DepthRim"}
]
```

路径是占位示例，不能直接执行。两组分别比较通过后再做 Combined。若基础图已有 rim，Baseline 也要通过独立材质变体明确关闭，不能把两个开启状态称作开关对照。

5. 默认直接加载 Open World 日光地图，不另建暗场景。深度边缘光仅在自有进程中临时设置并回读 `r.CustomDepth=3`，不写 DefaultEngine.ini。默认预览 stencil=1，构建候选的 stencil 配置须一致；若目标项目其它效果已用该 ID，应适配显式分配与过滤。每个 case 记录原生挂载回执，不能只根据 JSON 写了 enabled 判定生效。
6. 同视角/光照的 Lit 开关图必须实际打开：看全身及头发/脸/袜口等局部、不同距离与侧光；查看误描眼球/刘海、多层轮廓、厚边、光晕泄漏、遮挡。Unlit/WorldNormal 只作诊断；材质切换后继续等待贴图 mip。不能用大分辨率或发光补救模糊/错误光照。

当前预览支持对象形式的分槽 Overlay，见必读 [面部描边与嘴角黑点](face-outline-overlay.md)。按真实模型校准局部抑制，显式传入脸/发材质与排除槽；不能让全槽通用候选冒充已完成分区。深度边缘候选只是屏幕深度效果，不自动遵守角色光向；若目标要方向性 rim，另做光向约束或材质算法并验证。

## 可复用交付，不止预览

游戏使用新增强制区分，见 [重点材质效果与游戏验收](material-quality-contract.md)：`material_acceptance`、每项 `game_validation` 及六类测试报告。静态交付允许明确待测，不允许把静态挂载回执当作 game_ready；性能需使用启用效果后的实际版本及同条件开关对照。

交付 v2 必须包含 `scene_effects.outline` 和 `.rim`。

- 采用：`status=reviewed`，关联已视觉审阅的 `effects` 条目、`reason/evidence`、`method=outline/depth_rim/alternative`。原生方法要求报告中同条件 Baseline/candidate 的 Lit 截图和实际挂载回执；替代算法另写 `implementation`，仍要已有 effect 的 A/B 证据。
- `runtime_binding` 记录接入组件/Actor/BP、材质、槽/排除项、stencil、后处理混合权重等；给出可重复运行的配置/脚本或已有 BP 路径。此文本不代表运行时已经验证，要另注明运行时状态和测试。
- 不采用：`status=not_selected`，附当前模型/风格依据和已登记的 evidence ID；不能仅写“可选”。用户明确要求的效果若未完成，应 pending/blocked 并写 next_action，不能擅自改为不采用。

检查器只核对决策与证据关联，不能判断理由是否合理、算法是否漂亮、游戏 BP 是否真的接好。最终 agent 必须看图与回读，缺动态/性能测试单独列出。新效果的额外绘制/后处理成本要加入之后的同条件性能测试，不能沿用未启用效果时的 FPS。

## 旋转 API 防回归

UE Python 构造旋转必须写 `unreal.Rotator(pitch=..., yaw=..., roll=...)`，无旋转则 `unreal.Rotator()`；单位度。不能按 C++ FRotator 的直觉套位置顺序。日光首图保留模板三个轴，后续 yaw_offset 只影响 yaw；工具回读真实旋转，纯逻辑测试用 roll-first 绑定执行真实预览表达式并扫描全部便携 Python 调用。仍需在实际 UE 版本做亮度/天空的视觉验收。
