# 环境与执行

先确定三个独立路径：工作流仓库、目标 `.uproject`、源 PMX 包。不要从当前目录推断它们相同。移动到新电脑后更新角色配置的绝对路径；通用代码不改。复制整个工作流，不需要原 MMD2UE 工程。

本地 MMD2UE 开发约定：用户已指定后续实验默认在 `MMD2UE.uproject` 内完成，用新资产目录隔离，不新建测试工程。下列空白项目/插件打包步骤仅供用户明确要求的外部工程迁移，不作为本地实验默认步骤。MMD2UE 中直接编译现有 Editor 模块，姿态读取使用 `MMD2UERetargetTools`，不要安装重名 Runtime 插件。

1. `pmx4ue.py init` 生成角色 work order；需要真实 PMX、现有目标工程和按米计的 PMX 单位比例。`doctor` 只检查路径，不检查插件是否已编译。
2. Blender 3.6 配置可导入 `mmd_tools` 的环境。导入在独立后台进程完成，Blender 异常使用 `--python-exit-code 1` 返回失败。版本不符先做只读 API 探针，不自动下载安装。
3. `RunUAT BuildPlugin` 先在独立 HostProject 编译；本包的 Runtime 节点与 Editor 工具已经分离，Editor 依赖不会进入 Shipping Runtime。参照 README 的命令。
4. `maintenance/verify_plugin.py --engine <UE根> --plugin <打包输出> --output <新目录>` 创建空白验证工程并检查 Python API，不修改现有工程。源码/打包插件安装器拒绝覆盖已有目录；更新由 agent 审阅 diff 后单独处理。
5. 不要把本插件装进已含原 `FAnimNode_PmxFilteredRigidBody` 的 MMD2UE 工程。同名 UE 反射类型会冲突；新插件用于独立目标工程。

## 运行记录

`run --stage <名称>` 只预览；加 `--execute` 才运行。可用阶段见 `--help`。每次记录输入文件哈希、代码哈希、完整配置、输出哈希、进程返回状态和日志。输出存在时不重写；失败留下现场，由 agent 检查后选择新版本或明确的清理范围。

`status` 检测记录中输入/输出文件变化，但**不是完整依赖调度器**：它不自动检查 UE 内部资产是否被编辑，也不自动批准过期结果。改配置、脚本、贴图或 UE 资产后由 agent 判断需要重跑哪些阶段。`Saved/PMX4UE/.agent.lock` 防止多个运行器同时写工程；异常残留锁先核实进程，不盲目删锁。

运行器不启用 ForceMemoryCache、不改 RHI/质量、不锁 60 FPS。性能阶段启动自己拥有的临时编辑器，只关闭这一实例；不用用户当前场景。Windows 编译/.NET 启动若被宿主沙箱限制，应按宿主权限机制运行，不能不断重试弹出 dotnet 错误。

## 文件管理

建议角色工作单、决策/交接记录、经过审核的 rig/physics/material 配置进入该仓库 Git。源资产、绝对机器路径、生成物按团队权限选择是否提交；不要打包第三方模型。`.local/`、`runs/`、插件二进制/中间文件默认忽略。脚本库与角色配置可以独立演进，升级需保留旧成功版本。
