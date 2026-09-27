# v5：隔离脊柱链对腿部祖先的影响

日期：2026-09-27。状态：已保存、独立进程重载通过；用户随后反馈“效果很好”，授权提交整轮尝试。当前模型采用 v5 作为用户认可基线。

## 判断与范围

用户反馈 v4 姿态改善但行走仍偏移。目标骨架中 Center → Groove → Waist 下分 UpperBody 与 LowerBody；D 腿经 WaistCancel 挂在 LowerBody 下。LowerBody 没有独立重定向链并不意味着断开。Source spine_01 → spine_05 不包含双腿祖先，而目标旧 Spine 从 Groove 开始，包含 Waist。该语义差异是本轮对照假设，不把它当作已证实的全部原因。

按骨骼指引不改 mesh、骨架层级、权重或绑定姿态，不合并 LowerBody 和腿。

## 产物

- `Rigs/TPose_v5/IK_Tololo_UpperOnly_Spine_v5`：复制 v4 使用的 Target Rig，Spine 改为 UpperBody → UpperBody2。
- `Rigs/TPose_v5/RTG_UEFN_To_Tololo_TPose_v5`：复制 v4 RTG，更新顶层与各 Op 内部 Target Rig 引用，保留全部链映射。
- 完整 UE 路径前缀：`/Game/Characters/TololoSchool1001/`。
- 仍使用 `TPose_Source_v4` / `TPose_Target_v4`；本轮未重新生成姿态。

## 验证

`tools/ue_mmd2ue_spine_v5.py` 拒绝覆盖已有产物，验证链配置仅 Spine 起点变化、Center 骨盆不变、源 Rig/姿态名/Op 类型顺序与开关不变。原 mesh、Skeleton、Rig、v4 RTG 的哈希未变。命名姿态原生位置差 0 cm，旋转误差 < 0.000004°。独立 UE 进程通过 `PMX4UE_POSE_RELOAD=1` 再次确认持久化结果。78 项既有逻辑回归通过，不等同于动态验证。

## 用户验收与保留边界

用户查看 v5 后认可效果。本轮没有新增自动动画采样，不将用户的整体效果确认扩大为所有动画均已通过。进一步回归可使用相同 Walk 动画、时刻和预览偏移比较 v4/v5，关注骨盆→胸部、骨盆→髋部相对运动以及上下身连接。原 Root Motion 缺失目标根骨等警告未在此实验中处理。未逐字段审计所有 Op 设置；本轮通过复制保留设置且未主动编辑根运动参数。
