# PMX4UE

**Agent 主导的 PMX → Unreal Engine 角色转换工作台。**

脚本负责可靠地读取、转换、构建和测量；agent 负责理解模型、参考资料、选择方案、看效果，以及在必要时修改脚本。它不是把所有模型塞进同一套参数的一键导入器。

## 给没有上下文的 agent

把整个目录复制到目标工程旁边或工程内，然后提供这段任务：

> 阅读 PMX4UE/AGENTS.md 和 skills/pmx-to-ue/SKILL.md。目标 UE 工程是……，PMX 是……，参考效果是……。使用这个独立工作台完成角色材质、骨骼、IK 与 PMX 物理。先检查已有工具与模型证据，再建立角色配置；允许在 PMX4UE 内复制、修改、测试脚本。不覆盖原模型或正式资产。缺少动画、特殊关节支持或关键风格选择时明确列出，不把生成成功当成验收通过。保存决策、实验结果和接手说明。

## 当前结构

```text
PMX4UE/
├─ AGENTS.md                    agent 的工作边界与决策方式
├─ pmx4ue.py                    初始化、环境检查、分阶段运行、状态记录
├─ skills/pmx-to-ue/             短入口 + 分领域参考
├─ tools/                       UE 入口、IK、配置草稿工具
│  └─ legacy/                   已复制并适配的材质、骨骼、PMX 物理工具
├─ presets/materials.v1.json     可扩展的材质预设，不自动判定纹理用途
├─ unreal/PMX4UE/               独立 Runtime / Editor 插件源码
├─ templates/                   决策、特殊需求、交接记录
├─ tests/                       回归测试，不需要 UE 就能运行
├─ maintenance/                 源码归档、独立插件验证
├─ PROVENANCE.json              原始工具来源和复制时哈希
└─ VERIFICATION.md              此版本实际验证范围
```

角色配置建议放 `characters/<角色>/`，实验产物默认在目标工程的 `Saved/PMX4UE/<角色>/<版本>/`。这些目录在有真实角色任务时才创建，不附带模型、贴图或动画。`legacy` 是迁移来源标记，不表示禁止修改；旧 JSON schema 名称保留以兼容现有算法。

## 开始使用

依赖：Python 3.10+；Blender 3.6 与可用的 mmd_tools；UE 5.8 系列；构建插件需要匹配的 C++ 编译工具。其它版本应由 agent 先检查 API，必要时做版本适配。工具不替你下载软件或第三方素材。

在本目录执行，以下路径替换为本机实际路径：

```powershell
python pmx4ue.py init --id MyCharacter --pmx "D:/Assets/model.pmx" --project "D:/Projects/Game/Game.uproject" --scale 0.08 --blender "D:/Blender/blender.exe" --engine "D:/Epic/UE_5.8" --output "characters/MyCharacter/character.json"
python pmx4ue.py doctor --config "characters/MyCharacter/character.json"
python pmx4ue.py run --config "characters/MyCharacter/character.json" --stage audit --execute
```

`0.08` 只是示例，不是所有 PMX 的单位。agent 根据源模型尺寸确认后，才把 `pmx4ue.source_scale_reviewed` 设为 `true`。

```powershell
python pmx4ue.py run --config "characters/MyCharacter/character.json" --stage export
python pmx4ue.py run --config "characters/MyCharacter/character.json" --stage export --execute
python pmx4ue.py status --config "characters/MyCharacter/character.json"
python tests/run_tests.py
```

不带 `--execute` 仅输出命令和输入输出。每阶段单独执行，没有隐藏的“全部自动通过”。审核标记可以由 agent 根据证据填写，不要求用户替 agent 完成机械检查。

### 插件

先独立打包，再复制到目标空白工程；源码也可以通过工程自身构建。

```powershell
& "D:/Epic/UE_5.8/Engine/Build/BatchFiles/RunUAT.bat" BuildPlugin "-Plugin=$PWD/unreal/PMX4UE/PMX4UE.uplugin" "-Package=$PWD/.local/PackagedPlugin" -TargetPlatforms=Win64 -NoP4
python pmx4ue.py install-plugin --config "characters/MyCharacter/character.json" --source ".local/PackagedPlugin"
python pmx4ue.py install-plugin --config "characters/MyCharacter/character.json" --source ".local/PackagedPlugin" --apply
```

复制前关闭目标编辑器；安装只新增 `Plugins/PMX4UE`，不修改 `.uproject`，已有目标目录则拒绝覆盖。插件描述符启用了所需依赖。二进制必须匹配目标引擎版本；不要跨版本搬运本机编译产物。**原 MMD2UE 实验工程已包含同名动画节点，不要再往原工程安装本插件。** 本仓库本轮测试使用独立空白工程。

## 能完成什么、什么还需要 agent

- 脚本：PMX/贴图盘点、厘米导出、骨骼审计及有证据的上半身优化、材质构建、IK 配置、PMX 刚体/关节/碰撞组转换、独立物理资产与测试 ABP、数值及 PIE 性能测试。
- agent：材质槽与纹理语义、风格、骨骼角色和链条、重定向姿势、PMX 分区依据、特殊关节适配、视觉验收。可以修改脚本并补回归用例，而不是无限试参数。
- PMX 不含走路动画。没有提供动画时先完成可验证部分，明确“动态验收未完成”；不能拿静止结果冒充移动测试通过。当前物理构建包装器要求一条同骨架动画，agent 可增加有测试的 rest-only 分支，但不得伪造动态验收。
- 支持边界与版本实测见 [VERIFICATION.md](VERIFICATION.md)。现有成功案例不是其它角色必然 60 FPS 的承诺。

## 管理与拓展

这是独立 Git 仓库。角色差异首先放角色配置；多角色可复用的能力进入工具或预设；引擎差异进入明确的适配层。实验先建分支/新资产版本，小提交记录证据。一个 agent 写 UE 资产，其它 agent 可并行分析文档/只读报告，避免多进程争抢工程。

本目录没有包含 UE 引擎、mmd_tools 或第三方角色素材；它们遵循各自许可。`PROVENANCE.json` 是本项目工具的来源记录，不是第三方素材再分发授权。
