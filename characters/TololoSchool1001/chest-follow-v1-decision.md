# 胸部减晃数据变体：ChestFollow_v1

2026-09-27，未提交；用户正在游戏，仅做数据构建/静态检查，不做模拟或性能测试。

## 观察与选择

用户反馈胸部晃动过强。已认可的 Motion_v3 使用 Perf_v3 的6次迭代、60Hz延迟物理；本轮不混入尚未验收的 MotionPerf_v1 降迭代方案。

源 `Saved/PmxFullExperiment/independent_v3/manifest.json`：Chest_L/R 对应刚体196/197，质量各1，线性/角衰减0.5；碰撞group7、允许mask65407。关节325/326连接UpperBody2，旋转上下限均0，线性上下限相等，弹簧均0。线性锁定偏移非零（约0.872cm），不能简单说是零偏移固定关节。源数据不是显式弹簧晃动设计；当前大幅晃动原因仍未经过动态测量确认。

选择独立的 **跟随版**，而非声称调低阻尼即可解决：仅这两个刚体从动态变为kinematic，胸部骨由输入动画和父级驱动，保留碰撞shape及PMX过滤。取消两骨独立模拟及其锁定偏移的求解响应，是明确的模式覆盖，不是完全复刻PMX。若用户仍希望轻微弹性，应另建保留动态的阻尼/约束实验，不能把本版描述成保留弹性的减幅版。

## 产物

UE目录：`/Game/Characters/TololoSchool1001/PhysicsSandbox/Performance/ChestFollow_v1/`

- 使用 `ABP_ChestFollow_Travel`。
- 新外层资产 `PA_Outer_ChestFollow`，裙子仍直接引用原 `Perf_v3/PA_Deferred6_60_Skirt`。
- `ABP_Build_ChestFollow` 是生成中间件，不推荐使用。
- 不改原mesh、骨架、动画、场景，不覆盖用户已认可蓝图。

## 实现与检查

入口 `tools/ue_mmd2ue_chest_follow.py`。UE Python未暴露PhysicsAsset的body数组，首次只读探针失败且未创建资产。随后使用现有原生manifest importer重建独立PA，无需编译模块。manifest差分只允许两个kinematic标记及输出元数据；原碰撞pair、shape组/mask、关节记录完全保留。复制Perf_v3的solver_settings。

新建外层295动态体、22kinematic体、468关节、28484允许body对；连同原裙子的147动态体，预期总模拟骨骼由444变为442。新旧UE资产的可读取geometry、关节数量、solver检查一致；源资产哈希保持不变。完整序列化关节profile未直接暴露，不夸大为所有属性逐字节一致。

构建脚本运行完成并保存后，进程在Python清理阶段访问违规退出（exit1），不能把该次进程算作成功。后续 `tools/ue_mmd2ue_chest_follow_reload.py` 在新进程只读重载、检查输入输出哈希、geometry、solver和蓝图class，全部通过，进程exit0。移除了构建脚本在退出前持有的native方法包装引用作为清理防护，其是否消除构建退出故障尚未重跑验证。

证据：`Saved/PMX4UE/ChestFollow_v1/{manifest,build,reload}.json`；`Saved/Logs/PMX4UE_ChestFollow_v1*.log`。

验收状态：数据生成与新进程静态重载通过；动态视觉、runtime过滤应用与帧率未测试。不自动替换场景。等待用户方便时复核动作，保留Motion_v3随时对照。
