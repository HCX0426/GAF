---
date: 2026-08-28
symptom: [drf-decorator-order-typeerror, api-view-typeerror, permission-classes-order]
solution: DRF 装饰器顺序——@permission_classes/@throttle_classes 等必须置于 @api_view 之下（紧贴函数）；上层 extend_schema 等无碍但保持一致性
related_files:
  - backend/resources/views.py
  - backend/resources/urls.py
created_by: AI
priority: medium
n_id: N213
diff_keywords: ["api_view", "permission_classes", "extend_schema", "drf", "decorator"]
---

# DRF 装饰器顺序：@permission_classes 必须在 @api_view 之下

## 症状（2026-08-28 新增 template-match-preview 端点）

新增 `POST /resources/template-match-preview/` 后重启，整个 backend 500：`TypeError: @permission_classes must come after (below) the @api_view decorator. The correct order is: @api_view(...) 然后 @permission_classes(...)`；且异常发生在 URL 加载期 import `resources.urls` 时，**拖垮整个 API**（所有端口 200 接口全挂）。

## 根因

DRF 的 `@api_view` 返回一个包装函数，`@permission_classes` 等 policy 装饰器必须作用在该包装内才生效；若写成：

```python
@permission_classes([IsAuthenticated])   # ❌ 在上
@api_view(["POST"])                       # ❌ 在下 → TypeError
def view(request): ...
```

DRF 启动校验（`_check_decorator_order`）直接抛 TypeError → import 失败 → 全站 500。之前写法 `@extend_schema` 在上没问题，因为 extend_schema 不做顺序校验（但为一致也放在最上）。

## 解决方案（已实现）

正确的标准顺序（从上到下）：

```python
@extend_schema(...)              # 可选，放最上
@api_view(["POST"])              # 必须
@permission_classes([IsAuthenticated])  # 在 api_view 之下
def my_view(request): ...
```

## 泛化原则

任何新 DRF FBV 按模板写，不要凭记忆颠倒 api_view 与 policy 装饰器；后端 500 且日志指向 `urls.py` import 链时，第一嫌疑就是装饰器顺序 / import 语法错——修完必须重启 daphne（后端改动不热载，见 N209）。