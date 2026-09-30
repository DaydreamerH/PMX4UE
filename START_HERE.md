# 在目标工程使用 PMX4UE 0.2.0

这是源码工作台，不是携带角色资源的一键成品插件。脚本负责转换和测量，agent 负责模型判断、适配与视觉检查。

当前流程增加了上肢审阅执行检查，以及 [描边/边缘光场景闭环](docs/scene-effects-workflow.md)。旧工作单不能仅凭默认 preserve 进入 IK/物理；材质交付 v2 除 face_shading 外还要填写 scene_effects。迁移按领域参考补真实决策，不能自动把 pending 改成 reviewed。

## 你需要提供

1. 目标 UE 工程的 `.uproject` 路径。
2. PMX 及其完整贴图，保持原始相对路径。
3. 若需动态验收，提供源动画及其骨架；只有 PMX 可先完成静止部分。
4. 可选目标图/参考画面、目标平台、性能预算。目标图可直接放在 PMX 素材文件夹或其中的 targets/参考图 目录，agent 会按需发现、看图分区建档并在渲染时检索，无需逐张提供路径；没有适用图也能正常完成流程。见 [目标图建档](docs/target-image-lookdev.md)。

将整个 `PMX4UE` 文件夹放到目标工程内或旁边。无需复制任何历史工程的 Content/Saved；无需读取历史聊天。Python 3.10+、Blender 3.6+mmd_tools、UE 5.8 系列及匹配的 C++ 构建工具由 agent 检查。其它版本需明确适配。

## 交给 agent

填写并发送 [templates/import-agent.md](templates/import-agent.md)。入口顺序是：

`AGENTS.md` → `skills/pmx-to-ue/SKILL.md` → [执行手册](docs/fresh-project-runbook.md)。

agent 在本工作台运行 `init` 建立本机工单，检查工具与插件，按模型证据逐阶段执行。具体命令见 [README](README.md)。普通 `run` 是预览，加 `--execute` 才实际执行。

完整角色任务按 [多智能体协作规程](docs/agent-collaboration.md) 判断必要分工。主智能体从宿主实际选项匹配能力与成本，优先委派可独立完成的专项和原始证据审阅，统一安排 UE 操作；不需要用户指定模型名称或搭建团队。无委派工具则单智能体继续。

脸部阴影在首组材质基线后推进、静态材质交付前完成，见 [脸部专项](docs/face-shading-workflow.md)。`face-sdf` 入口只接入头骨方向驱动，贴图须另外生成/检查。交付清单已升级 v2，必须明确 SDF 或已验证的替代方案；白色占位图和关闭的开关不算完成。无动画不影响静态部分。

## 插件与更新

- 工作台 `unreal/PMX4UE` 是插件源码，不是已安装插件。按目标 UE 版本构建后安装到目标工程 `Plugins/PMX4UE`，或由目标工程编译源码。
- 不复用旧版本打包目录。0.2.0 包含物理 WorkflowTools 与头骨 SDF 组件，旧 DLL 缺少这些接口时必须重新编译。
- 已有插件目录不要直接覆盖；先核对本地改动和源版本，明确范围后更新。已有同名原生节点的工程不得重复安装。
- `capabilities` 验证核心桥接口，`face-sdf` 还会单独检查 SDF provider；阶段成功不等于视觉与游戏验收通过。
- 运行器不自动升级依赖或下载模型；缺少环境时说明具体缺项。
- Windows 构建可能需要经宿主审批访问工程外的 UBT 跟踪目录。出现 dotnet 弹窗时，按[环境参考](skills/pmx-to-ue/references/environment.md)诊断；不要反复重试、默认管理员运行或仅修改普通日志路径。

## 文件边界与完成标准

`tools/`、`unreal/`、`templates/`、`skills/`、`presets/`、`tests/` 是流程主体。`characters/` 和带案例路径的 `maintenance/workflow_*`、`tools/ue_mmd2ue_*` 是历史证据/复现入口，不得直接当成新模型配置。

源码 ZIP 由 Git 提交导出，不含 `.git`、`.local`、缓存、插件二进制或第三方模型。需要历史记录时克隆工作流仓库；需要快速复制时解压源码 ZIP 即可。

本版归档有效的导出、绑定修正、材质、重定向、动画、物理与 SDF 工具。新模型仍需分别验收材质外观、蒙皮/动作、碰撞及性能；不保证任意模型无适配运行，也不声称全部场景稳定 60 FPS。验证范围见 [VERIFICATION.md](VERIFICATION.md)。
