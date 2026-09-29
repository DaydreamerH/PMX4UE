# 动画驱动的 Face SDF（运行时协议 v1）

本阶段接入运行时方向驱动，不负责生成贴图。先按 [脸部阴影流程](face-shading-workflow.md) 完成真实 SDF 的数据检查、绑定及静态光照验收；无动画也要完成这些前置工作。Neutral 默认图不是此阶段的有效成品输入。

## 问题与约定

旧主材质的 `FaceForwardWS/FaceLeftWS` 名称虽含 WS，实际输入是参考姿态模型空间方向，后面接 Local→World。不能直接给这些旧参数写头骨世界方向，否则会二次旋转。Actor 朝向也不能代替头骨。

`tools/ue_face_sdf_runtime.py:add_runtime_basis` 只用于**复制后的主材质**。它按连接关系查找两条旧方向分支，插入以下协议，不改贴图、UV 镜像、SDF 阈值或光照来源：

- `FaceForwardRuntimeWS`、`FaceLeftRuntimeWS`：归一化世界空间方向，直接进入 SDF，不再次 Local→World。
- `FaceBasisRuntimeValid`：运行时有效为 1；默认 0，保留旧分支供未绑定预览使用。
- 缺少轴、非预期空间或重复修补都会拒绝执行；不要凭节点显示位置猜接线。

## 角色接入

本机适配位于 MMD2UE 的 `Source/MMD2UE/MMDFaceSDFComponent.*`；可迁移版本位于 `unreal/PMX4UE/Source/PMX4UE/{Public,Private}/PMX4UEFaceSDFComponent.*`，另附 PreviewActor。二者逻辑相同，仅类名和模块导出宏不同。组件可以加到 Character 或其它拥有 SkeletalMeshComponent 的 Actor；不是 CharacterMovement 的替代品。跨工程必须编译运行时模块，单独复制材质不够；MMD2UE 不安装重复插件。

1. 给角色的 Face 槽设置复制后的材质实例，其它槽不动；不要替换 mesh 资产的默认材质。
2. 添加 `MMDFaceSDFComponent`（本机）或 `PMX4UEFaceSDFComponent`（插件），明确指定 `SourceMesh` 和该模型的 `HeadBone`。通用默认骨名为空，不猜测另一模型也叫 Head。
3. `ReferenceForward/ReferenceLeft` 是**导入绑定姿态的模型空间面部轴**，不是头骨局部轴。可读取旧实例的 FaceForwardWS/FaceLeftWS 作起点，但 agent 必须结合模型正面、SDF 左右半球实际确认。Tololo 本次保持 `(0,1,0)` / `(1,0,0)`，没有擅自翻转贴图约定。
4. 运行时用 `CurrentHeadCS.Rotation * inverse(ReferenceHeadCS.Rotation)` 校准方向，再经组件世界旋转。只计算旋转，平移和非均匀缩放不应扭曲单位方向。
5. 组件在骨骼变换完成回调及 PostUpdateWork 更新，覆盖显式编辑器姿态求值和 Actor 移动；每个角色生成自己的 MID，不使用全局 MPC，不需要指定 KeyLight 才能更新头部。
6. 找不到头骨/轴退化时将 Valid 置零。解绑/组件注销会恢复其自己接管前的材质；不会覆盖用户之后主动换上的其它材质。

运行时 SourceMesh 在组件第一次更新时建立绑定。普通 AnimBP 编辑器预览不拥有这个角色组件，因此单独打开 ABP **不能**代表最终 SDF 验收。应运行配置好的角色 BP，或在预览宿主明确安装同等驱动。

## 通用工作流入口

在基础材质/骨架导入之后按需执行，不是所有 PMX 都需要 SDF：

1. agent 复制 `templates/face_sdf.example.json` 为角色配置，读实际 mesh、脸部材质槽、骨名、绑定姿态和 SDF 半球方向，填写 `review_evidence` 后设置 `reviewed=true`。示例双轴只是占位，不能直接视作另一角色的正确方向。
2. 配置 `provider=mmd2ue`（已有宿主适配）或 `pmx4ue`（其它工程编译的插件），明确 `mesh`、`face_slot`、`head_bone`、双轴、可选 `animation_blueprint`。动画蓝图应已重定向到该 mesh 的骨架。
3. `destination` 必须位于工单 `paths.ue_root` 下的全新子目录。给工单增加 `pmx4ue.face_sdf_profile`，值为审核后 JSON 的绝对路径。
4. 从 PMX4UE 根目录运行：

   ```powershell
   python pmx4ue.py run --config <角色工单.json> --stage face-sdf
   python pmx4ue.py run --config <角色工单.json> --stage face-sdf --execute
   ```

5. 输出 `face_sdf.json`：新 master、完整实例继承链、新 `BP_FaceSDF_Preview`；源资产指纹保持不变，不写 mesh 默认槽或关卡。已有输出拒绝覆盖，失败留下新变体与报告供诊断，不自动清理或重复补丁。
6. 将生成的 BP 放入获授权的测试关卡测试。正式 Character 使用同等组件绑定与脸材质覆盖；PreviewActor 不是移动角色控制器。没有动画配置时只是静态接入样本，不能验收动态效果。

脚本按连接关系识别现有 SDF 双轴分支；不匹配时停止，agent 应检查坐标空间并适配 `ue_face_sdf_runtime.py`，不能靠硬改节点坐标接线。还没有 SDF 贴图/基础图时先完成可选 SDF 烘焙与图构建，此阶段不会凭空产生正确的脸部阴影图。

构建成功只标记 `built_needs_runtime_visual_review`。依次验证编译、重载、骨骼实际运动→材质参数、Actor 转向/双实例隔离、同姿态旧新材质对照。新模型的视觉与运行时验收不能沿用托洛洛的通过报告。

## 本机入口与验证

- 首次构建：`tools/ue_mmd2ue_face_sdf_v1.py`（已存在命名空间时拒绝覆盖）。
- 仅恢复本次未完成实验：`tools/ue_mmd2ue_face_sdf_finish_v1.py`，核对源哈希后复测；并非通用覆盖入口。
- 视觉对照：`tools/ue_mmd2ue_face_sdf_visual_v1.py`，只在其拥有的临时编辑器世界运行，PIE 取当前头部姿态后冻结同一姿态，截图旧/新 Face 材质，不保存关卡。保持 `t.MaxFPS=200`，退出前恢复。
- 原生检查：`MMD2UEFaceSDFTools.test_face_sdf`，跨 120 帧真实步行动画检查当帧材质方向；另测非单位参考旋转、Actor+Head 合成、平移/缩放无关性、两角色 MID 隔离、缺骨回退和解绑恢复。
- 纯 Python：`python tests/run_tests.py`；图拓扑 fake 不替代引擎验证。

上述 `ue_mmd2ue_*` 是托洛洛实验复现入口，不是其它模型的配置模板。插件运行时来源与已编译的 MMD2UE 适配保持对应；独立插件构建/打包及其它 UE 版本仍需目标工程验证，不以复制源码当作跨工程验收。

动作角色验收还应覆盖转头、低头、翻滚、动画混合、LOD/隐藏后恢复以及多角色。移动的方向光由既有 SkyAtmosphereLightDirection 路径处理；此补丁未新增点光/聚光选择策略。

## 明确不变的内容

不改变 mesh、骨架、绑定姿态、动画、物理资产或碰撞组。不改变球形修正法线的中心和丝袜切线。当前修复针对面部 **SDF 朝向**；其它空间输入的问题需独立实验，不用本次结果宣称全部材质运行时需求已完成。
