# Agent 主导的通用 T-Pose 工作流

目标：**计算与安全检查通用，模型语义和效果由 agent 判断**。不是把托洛洛的骨名、旋转角或腿姿复制到其它角色，也不依赖 UE Auto Align。

适用：厘米制、单位骨缩放、双臂双腿的人形骨架。多足、缺肢、非单位缩放、非常规控制约束需显式适配，不能清空检查来强行通过。实验仍在 MMD2UE 原工程内，以新的 Rig/Retargeter 版本隔离；默认不提交。

## 文件与职责

建议角色档案和配对实验分开保存：

```text
PMX4UE/
  characters/<模型>/retarget/model.json     可复用的语义、身体坐标与证据
  characters/<模型>/retarget/decisions.md   agent 判断及特殊处理依据
  templates/retarget-agent.md              无上下文 agent 的接手任务
  tools/ue_pose_inventory.py               只读 UE 当前双侧姿态、Rig、链与映射
  tools/pose_workflow.py                   离线草稿、方案编译
  tools/retarget_workflow.py               语义合同、指纹、层级和效果门禁
  tools/retarget_pose_math.py              纯数学姿态求解
  tools/ue_retarget_pose.py                新建独立原生 Retarget Pose
  tools/ue_pose_reload.py                  新 UE 进程中的保存结果核验
<当前工程>/Saved/PMX4UE/Retarget/<配对>/<版本>/
  inventory.json
  draft/source.model.json, target.model.json, pair.json
  planned/pose_profile.json, plan.json, acceptance.json
  build.json, reload.json, views/, decision.md
```

模型档案绑定 mesh 和参考骨骼数据指纹，不绑定当前命名姿态；同模型换动画源可以复用。Rig 链名变化需要更新对应角色字段。配对方案绑定完整采集报告，当前姿态、链映射或已采集的 Op 类型/开关改变后必须重新采集和规划。

**指纹不是整个 uasset 的哈希**：当前不采集每个 Op 的全部内部参数、蒙皮权重、材质或动画轨道。它不能证明碰撞、运行时动画或 Rig 内部所有配置不变。agent 必须另外查看实际使用的各 Op Rig 引用、Pelvis/Root Motion 配置、权重审计和动画结果。

## 1. 在 UE 采集真实配对

已有重定向器先由 agent 核实实际 Source 动画骨架和 Target 模型。禁止用同一个模型两份 Rig 当作跨模型验证。在 UE Python 中导入工具目录后调用：

```python
import sys
sys.path.insert(0, r"D:/UEProjects/MMD2UE/PMX4UE/tools")
from ue_pose_inventory import export
export("/Game/实际配对重定向器", r"D:/实际输出目录/inventory.json")
```

替换上述路径。也可在单独 UE 命令行进程执行该脚本，输入环境变量 `PMX4UE_RETARGETER`、`PMX4UE_OUTPUT`。使用已有 `MMD2UERetargetTools` 原生读取桥，不安装重复插件。输出已存在则拒绝覆盖。

UE 采集不读取权重。角色存在普通腿/D 腿等双链时，agent 另查已有骨骼权重审计、导出记录或真实变形，不能仅按名称猜测。

## 2. 离线生成草稿，agent 填模型档案

以下命令在 PMX4UE 目录执行。`$run` 是本次独立输出目录，先有第 1 步的 inventory：

```powershell
$run = "D:/UEProjects/MMD2UE/Saved/PMX4UE/Retarget/MyPair/v1"
python tools/pose_workflow.py draft --inventory "$run/inventory.json" --source-id SourceModel --target-id TargetModel --output-dir "$run/draft"
```

草稿故意不猜骨名、不自动勾选审核。agent 填两份 `*.model.json`：

- `basis.left/forward/up`：实际组件空间身体方向，各为三维向量。左右指角色自身，不是屏幕左右。三轴必须正交；两侧可以不同。
- `roles.pelvis`：能驱动上下身的共同骨盆语义骨；与当前 Rig pelvis 一致。
- `roles.spine`：脊柱旋转链的起止骨。不能包含腿的祖先；例如某些 PMX 的 Waist 同时驱动腿，不能随便放入 Spine。
- `roles.arms/legs.left/right`：分别为上臂/肘/腕、大腿/膝/踝三个真实变形骨名。可跨过 twist/helper，但必须沿父子路径。
- `spine_chain`、`limb_chains.arms/legs.left/right`：实际 Rig 链名。工具核对端点以及 Source→Target 链映射。
- `role_evidence`：分别记录骨盆、脊柱、手臂、腿、坐标的证据路径与判断。使用真实审计或截图，不填写“已检查”代替依据。
- `review`：审核者、理由、证据列表、尚未解决项。agent 可以审核，只有重大歧义或风格选择才询问用户。

若链语义不对：用已有 IK 工具或受测适配器创建**独立** Rig/Retargeter，同步各 Op 的 Rig 引用，重新采集。此工具不会替你修改已有骨架、合并 LowerBody 或删除腿骨。

## 3. agent 填配对方案，离线预演

`pair.json` 中填写新的 `namespace`、`output_retargeter`、双侧 `pose_name`。当前 UE 写入入口要求输出包路径和姿态名使用英文、数字和下划线。

每侧决策：

- `restore_reference_rotations`：仅显式恢复有依据的旧姿态偏移，不能整骨架清零。
- `pre_edits`：腰、骨盆、锁骨等在四肢求解**之前**的修正。
- `edits`：求解之后的掌心、脚掌等微调。格式沿用 [逐骨旋转](retarget-pose.md) 的 `add_local` 或 `set_offset`；局部轴不同，不能跨模型复制 Euler 数值。
- `edit_reasons`：以上每个显式修改/恢复的骨骼必须有理由。共用父骨修改后，agent 需排查子骨骼遗留补偿。
- `posture_checks`：至少一项真实躯干关节连线，字段 `start`、`end`、`up_axis`、`max_tilt_degrees`。根据模型自然曲线设阈值，不默认所有角色腰颈垂直。

站姿策略：`stance.mode=match` 选择 `reference_side`，把该侧经过基底修正的腿段方向，通过身体坐标转换给另一侧。保持骨长、髋宽和脚掌组件旋转，不强制不同体型脚踝坐标完全重合。`preserve` 明确保留各自腿姿，需要 agent 说明为什么无需匹配。脚底实际接触、内外八及膝朝向仍需视觉判断。

求解顺序：显式恢复 → pre_edits → 双臂水平 → 双侧腿段匹配 → 手脚微调 → 全身指标检查。最终偏离已求解四肢方向超过 `max_segment_error_degrees` 会拒绝写入；不要为了掩盖明显错误放宽阈值。

```powershell
python tools/pose_workflow.py plan --inventory "$run/inventory.json" --source-model "$run/draft/source.model.json" --target-model "$run/draft/target.model.json" --pair "$run/draft/pair.json" --output-dir "$run/planned"
```

生成 `pose_profile.json`（可执行）、`plan.json`（预测数据和警告）、`acceptance.json`（待验收清单）。这一步完全离线，不启动 UE，不生成资产。审核后修改了方案则使用新的 planned 目录重新编译，不手改生成的 profile。

## 4. 原生写入与持久化验证

将 `pose_profile.json` 的绝对路径填入角色配置 `pmx4ue.retarget_pose_profile`，继续用已有 `pmx4ue.py run --stage retarget-pose` 预览/执行。运行器的 `paths.ue_root` 必须与 pair namespace 一致；按运行器自己的 `/Game/PMX4UE/<角色>/<版本>` 约定设置。MMD2UE 现有 Characters 目录实验可在 UE 中直接调用：

```python
import json
from pathlib import Path
from ue_retarget_pose import build
profile = json.loads(Path(r"D:/实际输出目录/planned/pose_profile.json").read_text(encoding="utf-8"))
build(profile, profile["agent_contract"]["pair"]["namespace"], r"D:/实际输出目录/build.json")
```

写入前重新采集原生数据、重编译审核方案，并对比可执行 profile；失效指纹或被手改的结果会在复制资产前被拦截。保持旧版手写 profile 兼容，但旧入口不具有新的角色审核合同保障。

成功仅代表新资产保存和当前进程原生读回通过。以后在**新启动的 UE 进程**中调用 `ue_pose_reload.check(build_report_path, new_reload_report_path)`；也可执行 `ue_pose_reload.py`，环境变量为 `PMX4UE_POSE_BUILD_REPORT`、`PMX4UE_OUTPUT`。脚本拒绝与生成进程相同的 PID；调用者仍须保证这是新启动的进程，而不是另一个已经缓存资产的编辑器。

重载不会写 UE 资产，只核验双侧姿态、mesh、根偏移及原始姿态未变，生成独立报告。生成失败的部分新资产标记为 `failed_do_not_use`，不自动删除、重试覆盖。

## 5. agent 负责效果闭环

1. 正面、侧面、手掌/肩、鞋底截图。关节水平不等于袖子形状自然；保留合理的模型差异。
2. 播放同一 Source 的 idle、walk、转身/急停；必要时加大幅动作。检查上下身连接、LowerBody、足滑、掌心和持续根位移。
3. `test_animations` 填真实资产路径。没有动作或不能启动 UE 时明确 pending，不用静态图冒充动态验收。
4. 将 build/reload 报告和截图、动画证据写入 acceptance/decision。`native_readback` 与 `fresh_reload`、视觉、动画、用户认可分别记录，绝不一起自动置为通过。
5. 效果不合格由 agent 比较数值与画面，修正模型角色或配对参数，输出新版本。需要新算法时先在工具内补测试，再推广；不要塞进模型名分支。

## 当前验证边界

2026-09-27 补充真实集成验证：通用 inventory→model/pair→compile→build→新进程 reload 已在 UEFN→托洛洛实际不同骨架上通过。新资产 `/Game/PMX4UE/WorkflowPoseProbe/v1/RTG_AgentContract`；重载位置误差 0，旋转误差 <0.000003°。报告在目标项目 `Saved/PMX4UE/WorkflowPoseProbe_v1`。不是新模型全链视觉验收；已有 v5 用户认可不能替代其它模型结果。离线仍覆盖异名骨架、体型/方向、Scale=100、错误链、腿祖先、指纹、修正顺序及拒绝覆盖。
