# 面部 Overlay：嘴角黑点的诊断、校准与挂载

Overlay 是额外绘制层，不是自动消除黑点的算法。先做同机位 Lit 无描边/通用描边对照：关闭描边后仍有黑点，检查原贴图、嘴腔/重叠几何、法线与阴影，不用描边遮罩掩盖。仅开启后出现时检查逆壳挤出、嘴角内表面、槽位误挂与透明排序。

## 按实际模型校准

独立嘴腔、牙齿、眼球等槽可按证据排除；嘴角与脸共槽时用局部遮罩，不把整张脸隐藏。内置候选把各 UV 椭圆的外侧系数相乘，接入面部 Overlay 的 Opacity；不改基础肤色、SDF 或 mesh。检查正常唇线与下颌轮廓未被抹去。

在工单 `features.outline` 填 `face_width`、`face_uv_channel`、`face_internal`。每个区域格式为 `{"name":"MouthCornerL","center":[u,v],"radius":[ru,rv]}`，必须来自当前模型 UV，半径须正数。非空区域还须 `face_internal_reviewed:true` 和 `face_internal_evidence`（真实 UV 审计/标注路径与判断）。复杂 UV 或表情下椭圆不适用时，agent 应适配纹理/顶点权重遮罩及对应绑定，不照搬别的角色。

默认区域为空，面部抑制关闭，**不再自动套用旧椭圆坐标**。旧工单若填了区域，需复核后补校准证据，不能机械勾选 reviewed。报告记录区域、通道和启用状态，但配置审核不等于视觉通过。

## 分槽挂载

预览 case 的 outline 支持对象形式。以下索引和路径仅展示语法，必须替换为实际模型值：

```json
{
  "name": "OutlineFaceControlled",
  "slots": [],
  "outline": {
    "material": "/Game/Character/Materials/MI_Outline",
    "face_material": "/Game/Character/Materials/MI_Outline_Face",
    "face_slots": [0],
    "hair_material": "/Game/Character/Materials/MI_Outline_Hair",
    "hair_slots": [3],
    "excluded_slots": [1, 2]
  }
}
```

材质和对应槽必须成对填写；脸/发/排除组不能重叠。工具核对索引范围，编译并记录三个材质的依赖，实际传入原生分槽 Overlay 接口，校验回执的材质及应用/排除槽。切换 case 清除上一组 Overlay；不保存关卡或原 mesh。旧 outline 字符串仍表示全槽通用候选，不代表面部抑制已开启。

`requested_routing` 只是请求配置；当前原生回执报告材质路径及应用/排除槽，不是脸/发的逐槽引擎读回。不得据此伪称完整逐槽验证，实际面部效果仍需看图。

## 验收与交付

最小静态对照为无描边、通用描边、校准后的面部描边三组同条件 Lit；拍正面和斜侧嘴角近景，并检查下颌轮廓，记录黑点、唇线丢失、接缝和侧面漏线。非必要不拍 Unlit/WorldNormal。默认日光场景及默认曝光政策不变。

有表情则加闭口/张嘴/微笑验证；无动画不阻止静态测试，但表情稳定性须列为待验，不能称为 game_ready。最终 runtime_binding 包含脸/发专用材质、对应槽、排除项及参数/校准记录，不能只交付通用 MI。构建成功或黑点从某个视角消失都不等于验收完成。
