# 0.1.0 验证记录

日期：2026-09-26。此文件区分原工程经验与**复制后的独立工作流**实测。

## 本轮独立验证

环境：Windows 11，Blender 3.6.23，UE 5.8.2 (`56702186`)，MSVC 14.44 / Windows SDK 10.0.22621.0。

| 检查 | 结果 | 边界 |
|---|---|---|
| `python tests/run_tests.py` | 64 项通过 | 纯逻辑/运行器，不代表画面合格 |
| Python compileall | 通过 | 仅语法 |
| skill-creator quick_validate | 通过 | 技能入口结构，不代表 agent 行为已完成跨模型验证 |
| 独立 RunUAT BuildPlugin | Editor、Game Development、Game Shipping 均通过，退出 0 | 编译，不是打包游戏帧率 |
| 空白项目插件加载/API probe | 通过，退出 0 | 无原 MMD2UE 模块或内容依赖 |
| 托洛洛原 PMX → 独立 Blender/FBX | 通过，退出 0 | 未修改源 PMX；不携带模型到仓库 |
| FBX 单位契约 | 单位系数约 1；mesh/armature scale 1；Center 位移 84 cm | 局部样本与 root 检查，不代替 bind/动画 |
| 新目录 PMX physics inventory | 通过 | 只读取物理数据，未在新工程重做动态物理 |
| 材质未审核草稿、骨骼审计、配置草稿 | 生成成功 | 草稿未假装审核完成 |
| 空白工程 FBX 导入 + C++ 骨架检查 | 导入成功，组件空间非单位缩放骨骼为 0 | **有绑定姿态警告，见下方** |
| 配置驱动目标 IK Rig | 7 条链 + Center pelvis 创建、保存通过，退出 0 | 未导出动画；未宣称重定向视觉通过 |
| 原工具来源哈希复核 | 复制来源无变化 | 本轮未改写原工程工具 |

实际测试生成物留在本机 `.local/BlankProbe_v2/`，不提交，也不是便携工作流的运行依赖。空白工程只使用 PMX4UE 插件；导入只写 `/Game/PMX4UE/TololoProbe/v1/`。

本轮发现并修复：Blender 导出脚本的旧包路径、物理盘点对托洛洛脚本的数学函数依赖、材质预设绝对定位、基准测试的专用资产 fallback、UE `SkeletalMesh.get_all_bone_names` 不存在（改用插件只读检查接口）、UE object path 与 package path 比较差异。

## 没有解决/没有重新验收的内容

1. 空白工程 Interchange 导入日志仍有 `Imported skeleton has some invalid bind poses`，引擎使用时间零姿态重绑；另有 MikkTSpace `zero length normal` 消息。**导出基线尚不能标为生产级绑定姿态验收通过。** 已附 `blender_audit_fbx_bind_pose.py` 供 agent 后续分析，不能通过隐藏警告冒充修复。
2. 新包装未在全新项目重新验收完整材质外观、上半身修改后的所有动作、重定向导出、裙子/外套/头发模拟及 PIE/打包性能。旧项目的成功效果不能自动转移为此版本的全链通过。
3. 物理底层来自已有 native RigidBody 方案，碰撞/关节/参数计划有回归测试；PMX mode 2 等特殊语义仍需适配。不是任意 PMX 的完全等价 Bullet 复刻。
4. 未进行独立无上下文 agent 的真实跨模型全链测试。本轮提供了完整交接入口、脚本和报告机制，但不把它称为已经验证的任意角色一键转换。
5. 原性能案例曾在报告生成后发生编辑器退出崩溃；运行器保留非零退出失败判断，未在本轮证明关闭问题已修复。

## 下一次最有价值的验证

由新 agent 使用一个新角色 PMX 和空白工程，根据 README 建立工作单，逐项记录 material / bind pose / retarget / physics / performance 结果；只为真实遇到的差异修改脚本。绑定姿态问题优先定位；不能跳过后直接宣称整套流程可投入游戏。
