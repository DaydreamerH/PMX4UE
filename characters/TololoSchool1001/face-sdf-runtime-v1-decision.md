# Face SDF 头骨驱动 v1 — 2026-09-27

## 观察 → 假设

用户观察到动画移动/转身时 SDF 像停在初始方向。旧材质将 FaceForwardWS/FaceLeftWS 当模型空间方向；旧 MMDToonCharacterActor 则用 Actor 世界旋转写入这些参数。二者既不表达动画头骨，又存在重复变换风险。物理测试的 SkeletalMeshActor 没有该旧 Actor 更新器。

## 最小变更

保持获认可的 `SK_TololoSchool1001_UpperOnlyCm_v1`、`ABP_ChestFollow_Travel` 和步行动画。新建：

`/Game/Characters/TololoSchool1001/PhysicsSandbox/Materials/SDFHead_v1/`

- `M_Face_HeadDriven`：复制旧 master，新加运行时世界空间双轴分支。
- `MI_Face_HeadDriven`：复制原 Face 实例并换为新 parent，保留原参数和贴图。
- `BP_Tololo_HeadSDF`：继承新增的 MMDFaceSDFPreviewActor，Face 槽覆盖新实例，仍用最新胸部跟随物理 ABP。

只新增 MMD2UE 原生 SDF 组件、预览载体和最小编辑器验证接口；未修改历史案例工具/旧 Actor，也未写用户关卡。Head 映射为 `Head`，参考正面 +Y，SDF 半球轴 +X，按原实例继承。

## 对照实验

1. 当前 UE 5.8.2 Development Editor 编译成功，PCD3D_SM6 新主材质编译零错误。
2. 首轮 `Saved/PMX4UE/SDFHead_v1/build.json` 保留失败结果：命令行创建的无 GameMode 世界没有派发完整 BeginPlay，驱动未持续更新。修复测试世界启动，并加骨骼求值完成回调；未通过放宽断言掩盖问题。
3. 新进程 `runtime_v2.json`：120 帧真实步行、两个 Actor 旋转不同，材质方向与当帧头骨期望值最大向量误差 `2.48e-15`，运动方向变化量 `0.1550`。全部断言通过，缺骨回退/解绑恢复/实例隔离通过。
4. 新编辑器进程重新加载 BP，实际 PIE 使用 `ABP_ChestFollow_Travel_C`，骨名与材质有效标志正确；固定同一动画姿态、相机、方向光，只替换旧/新脸材质。`visual.json` 记录输入哈希不变。
5. agent 已检查 `Saved/MMD2UECaptures/SDFHead_v1_new.png` / `SDFHead_v1_old.png`：同一姿态下新材质按当前头部与光照关系变暗，旧材质仍偏亮，头部几何/构图一致。截图证明动态分支有可见影响，不代表所有转头角度和极端动作均已验收。
6. PMX4UE 全部 118 个 Python 测试通过（含新增 4 个图拓扑/拒绝条件测试）。

## 结论与使用

本轮头骨→材质的动态连接及角色重载已验证。将上述 `BP_Tololo_HeadSDF` 拖入关卡，运行即可；仅拖原 ABP 不会自动安装驱动。未切换用户现有场景。后续按用户“接入工作流提交”的要求，将本轮 SDF 变更单独提交，保留其它未提交内容。

仍待：用户在实际动作集内视觉确认；多 LOD/隐藏恢复与打包游戏测试。CharacterMovement/真正根运动消费不在本次范围，球形法线中心/丝袜方向也未修改。不要将“渲染可见且动态数值通过”写成完整动作游戏角色已验收。

环境：期间一次 dotnet 异常弹窗没有取得可归因的系统日志；后续构建成功。UE Zen 缓存继续报告 HTTP 507，C 盘余量约 1.46GB；未擅自清理用户缓存或改变画质/RHI。本轮不是性能测试。

## 工作流集成复测（2026-09-27）

- 新入口 `face-sdf`，配置示例 `templates/face_sdf.example.json`。运行时组件与预览 Actor 已复制到 PMX4UE Runtime 模块，4 个文件经类名/导出宏规范化后与已编译 MMD2UE 适配一致；没有向 MMD2UE 安装插件。
- MMD2UE UE 5.8.2 新命名空间：`/Game/PMX4UE/TololoSchool1001/SDFWorkflow_v1/FaceSDF_v1`，由通用脚本生成 `M_Face_HeadDriven`、`MI_Face_HeadDriven`、`BP_FaceSDF_Preview`。这是同一模型的流程回归，不是第二模型/空白工程通过。
- 以 `Saved/PMX4UE/SDFWorkflow_v1/config.json`、`face.json` 作为 `PMX4UE_CONFIG`、`PMX4UE_FACE_SDF_PROFILE`，`PMX4UE_STAGE=face-sdf`，`PMX4UE_SCRIPT=PMX4UE/tools/ue_face_sdf_workflow.py`，`PMX4UE_OUTPUT=Saved/PMX4UE/SDFWorkflow_v1/build.json`，通过 `ue_entry.py` 在 `UnrealEditor-Cmd -run=pythonscript -AllowCommandletRendering` 执行。正式工单由 runner 注入这些变量，绝对机器路径不进入通用模板。
- `build.json`：PCD3D_SM6 零编译错误，保护的 mesh/原材质链/物理 ABP 指纹不变。支持复制完整实例继承链，避免只换 leaf parent 丢失继承参数；本次实际模型使用单层实例，多层继承尚未做 UE 个案回归。
- 新进程 `reload_runtime.json`：生成 BP 默认 mesh、物理 ABP、Head、Face 槽和双轴重载一致；新材质实际步行 120 帧测试通过，最大向量误差 `2.48e-15`，方向变化 `0.1550`。测试运行于原生临时 Actor；不是新 BP 的完整 PIE 动作集验收。
- 本工作树 123 项 Python 测试通过，其中 9 项 SDF 测试覆盖语义接线、重复/错误空间拒绝、审核/命名空间、非英文骨名、非法轴与阶段 dry-run。脚本测试不替代引擎和视觉检查。
- 新通用变体仍标记 `built_needs_runtime_visual_review`；本轮未重复截图，已有视觉证据仅对应前述 SDFHead_v1。插件独立构建/跨工程打包、其它模型与动作集均不宣称通过。
- 生成的示例 BP 依赖本地已认可的托洛洛 mesh/ABP；工作流代码不附带或隐式复制第三方模型，迁移到别的项目须提供该项目自己的输入。
