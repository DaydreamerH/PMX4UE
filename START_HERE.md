# 在目标工程使用 PMX4UE 0.2.0

这是源码工作台，不是携带角色资源的一键成品插件。脚本负责转换和测量，agent 负责模型判断、适配与视觉检查。

## 你需要提供

1. 目标 UE 工程的 `.uproject` 路径。
2. PMX 及其完整贴图，保持原始相对路径。
3. 若需动态验收，提供源动画及其骨架；只有 PMX 可先完成静止部分。
4. 可选参考画面、目标平台、性能预算。

将整个 `PMX4UE` 文件夹放到目标工程内或旁边。无需复制任何历史工程的 Content/Saved；无需读取历史聊天。Python 3.10+、Blender 3.6+mmd_tools、UE 5.8 系列及匹配的 C++ 构建工具由 agent 检查。其它版本需明确适配。

## 交给 agent

填写并发送 [templates/import-agent.md](templates/import-agent.md)。入口顺序是：

`AGENTS.md` → `skills/pmx-to-ue/SKILL.md` → [执行手册](docs/fresh-project-runbook.md)。

agent 在本工作台运行 `init` 建立本机工单，检查工具与插件，按模型证据逐阶段执行。具体命令见 [README](README.md)。普通 `run` 是预览，加 `--execute` 才实际执行。

## 插件与更新

- 工作台 `unreal/PMX4UE` 是插件源码，不是已安装插件。按目标 UE 版本构建后安装到目标工程 `Plugins/PMX4UE`，或由目标工程编译源码。
- 不复用旧版本打包目录。0.2.0 包含物理 WorkflowTools 与头骨 SDF 组件，旧 DLL 缺少这些接口时必须重新编译。
- 已有插件目录不要直接覆盖；先核对本地改动和源版本，明确范围后更新。已有同名原生节点的工程不得重复安装。
- `capabilities` 验证核心桥接口，`face-sdf` 还会单独检查 SDF provider；阶段成功不等于视觉与游戏验收通过。
- 运行器不自动升级依赖或下载模型；缺少环境时说明具体缺项。

## 文件边界与完成标准

`tools/`、`unreal/`、`templates/`、`skills/`、`presets/`、`tests/` 是流程主体。`characters/` 和带案例路径的 `maintenance/workflow_*`、`tools/ue_mmd2ue_*` 是历史证据/复现入口，不得直接当成新模型配置。

源码 ZIP 由 Git 提交导出，不含 `.git`、`.local`、缓存、插件二进制或第三方模型。需要历史记录时克隆工作流仓库；需要快速复制时解压源码 ZIP 即可。

本版归档有效的导出、绑定修正、材质、重定向、动画、物理与 SDF 工具。新模型仍需分别验收材质外观、蒙皮/动作、碰撞及性能；不保证任意模型无适配运行，也不声称全部场景稳定 60 FPS。验证范围见 [VERIFICATION.md](VERIFICATION.md)。
