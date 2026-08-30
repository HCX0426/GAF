"""P0-6 target / target_offset resolution utility.

MaaFramework Pipeline Protocol semantics: every action node can specify a
`target` config that points to a recognition result (or a context variable
holding a position) instead of hardcoding x/y. An optional `target_offset`
adds a delta to the resolved position.

Conventions:
- `target` may be:
  - The string "_last_match_pos" (default): use the last recognition result
    position automatically published by recognition nodes.
  - The string "_anchor_pos": use the position published by AnchorNode.
  - A "${var_name}" reference: resolve from context variable.
  - A dict {"x": int, "y": int}: literal position.
  - None / omitted: fall back to the node's own x/y config (legacy behavior).

- `target_offset` may be:
  - A dict {"x": int, "y": int}: applied to the resolved target.
  - A list/tuple [x, y]: applied to the resolved target.
  - None / omitted: no offset applied.

Recognition nodes publish `_last_match_pos` automatically via
`publish_match_pos()` after a successful match.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from engine.context import PipelineContext

# Reserved context variable names.
LAST_MATCH_POS_VAR = "_last_match_pos"
ANCHOR_POS_VAR = "_anchor_pos"

TargetSpec = str | dict[str, int] | None
OffsetSpec = dict[str, int] | tuple[int, int] | list | None


def publish_match_pos(context: PipelineContext, x: int, y: int, *,
                      source: str = "", extra: dict[str, Any] | None = None,
                      var_name: str = LAST_MATCH_POS_VAR) -> None:
    """Publish a recognition result position to a context variable.

    Recognition nodes (template_match, feature_match, ocr, color_detect,
    anchor, etc.) call this after a successful match so downstream action
    nodes can resolve `target` without explicit variable wiring.

    坐标系契约 (N191 §10.7 修正, 2026-07-27):
        x, y 的坐标系取决于 device + coord_transformer 组合:
        - Windows + coord_transformer (transformer 路径): **LOGICAL** (client)
        - Windows + 无 coord_transformer (legacy 路径): raw pixel (DPI=100% 时
          ≈ logical; DPI>100% 时是 physical, 已知限制)
        - ADB + coord_transformer (N191 §10.7 新增 ADB 路径): **PHYSICAL**
          (按 device.physical_res / base_res 缩放后的 physical 坐标)
        - ADB + 无 coord_transformer (legacy): **PHYSICAL** (raw pixel)

        下游 resolve_target 返回相同坐标系, device.click/swipe 期望相同坐标系,
        契约一致。原 docstring 写 "screen coords" 误导 — 实际不是 SCREEN
        (绝对屏幕坐标), 而是 LOGICAL (Windows) 或 PHYSICAL (ADB)。

    N191 §10.7 P0-1 自动 coord_system 注入:
        发布的 pos dict 自动带 coord_system 字段, 取值来自 context.coord_system
        (由 orchestrator 注入)。下游 set_variable / structured_logger /
        resolve_target 可读到坐标系标签, 无需节点单独传参。

    N191 §10.7 P0-1 架构层补漏 (2026-07-27): 新增 var_name 参数。
        AnchorNode 之前直接 set_variable("_last_match_pos", {"x","y"})
        绕过本函数, 导致 coord_system 字段丢失。现在 AnchorNode 改用
        publish_match_pos(var_name=output_variable) 走统一入口, 保证所有
        位置发布都带 coord_system 标签。其他识别节点不传 var_name, 默认
        写 _last_match_pos (向后兼容)。

    Args:
        context: Pipeline execution context.
        x, y: Center coordinates of the match (logical on Windows with
            transformer, physical on ADB / Windows legacy)。
        source: Optional source node id / node_type for debugging.
        extra: Optional extra fields merged into the published dict.
        var_name: Target context variable name. Defaults to
            ``_last_match_pos`` (recognition nodes). AnchorNode passes
            ``output_variable`` (default ``_anchor_pos``) so downstream
            nodes can resolve via ``${_anchor_pos}`` and the published
            dict carries coord_system automatically.
    """
    pos: dict[str, Any] = {"x": int(x), "y": int(y)}
    # N191 §10.7 P0-1: 自动注入 coord_system 标签。
    # 若 context.coord_system 未设置 (老路径/测试), 不强制写空字符串,
    # 保留 pos 干净; 若有值则透传。
    coord_system = getattr(context, "coord_system", "") or ""
    if coord_system:
        pos["coord_system"] = coord_system
    if source:
        pos["source"] = source
    if extra:
        pos.update(extra)
    context.set_variable(var_name, pos)

    # N191 §10.10 决策点 1 (AI 可调试性, 2026-07-27):
    # publish_match_pos 是识别节点→动作节点的核心坐标传递入口, 必记
    # trace。AI 调试时通过 grep "publish_match_pos" 看每个识别节点发布
    # 的坐标 + 坐标系标签, 不需要重跑就能反推点击位置 (D4 bug 现场重建)。
    # raw=None 表示 publish 是首次写入 (无上游转换); converted=pos 本身。
    try:
        context.emit_coord_trace(
            node_id=source or "unknown",
            step="publish_match_pos",
            raw=None,
            converted=pos,
            formula=f"publish({var_name}) with coord_system={coord_system or 'legacy'}",
            coord_system_in="",
            coord_system_out=coord_system,
            extra={"var_name": var_name, "source": source} if source else {"var_name": var_name},
        )
    except Exception as e:
        # best-effort: trace 失败不影响 publish 主流程。
        logger.debug("emit_coord_trace failed for publish_match_pos: %r", e)


def resolve_target(context: PipelineContext,
                   target: TargetSpec,
                   offset: OffsetSpec = None,
                   fallback_x: int | None = None,
                   fallback_y: int | None = None) -> tuple[int, int]:
    """Resolve a (x, y) coordinate from a target spec + offset.

    Args:
        context: Pipeline execution context.
        target: Target spec (see module docstring).
        offset: Optional offset spec applied to the resolved target.
        fallback_x, fallback_y: Used when target is None/empty and the
            caller wants to fall back to literal coordinates.

    Returns:
        Tuple (x, y) of resolved screen coordinates.

    Raises:
        ValueError: When the target cannot be resolved (missing variable,
            malformed dict, etc.).
    """
    x: int | None = None
    y: int | None = None

    if target is None or target == "":
        # Fall back to literal coordinates.
        if fallback_x is not None and fallback_y is not None:
            x, y = int(fallback_x), int(fallback_y)
        else:
            raise ValueError(
                "target is None and no fallback (x, y) provided"
            )
    elif isinstance(target, dict):
        # Literal position dict.
        if "x" not in target or "y" not in target:
            raise ValueError(f"target dict missing 'x'/'y': {target!r}")
        x = int(target["x"])
        y = int(target["y"])
    elif isinstance(target, str):
        name = target.strip()
        var_name = name[2:-1] if name.startswith("${") and name.endswith("}") else name
        var_value = context.get_variable(var_name)
        if var_value is None:
            raise ValueError(f"target variable {var_name!r} not found in context")
        x, y = _extract_xy(var_value, var_name)

        # P0-7 fix (AI 可调试性, 2026-07-27): 跨设备坐标系混合校验。
        # 若 var_value 含 coord_system 标签且与当前 context.coord_system
        # 不一致, 说明识别节点 publish 时的坐标系与动作节点 resolve 时的
        # 坐标系不匹配 (例如 ADB 节点 publish PHYSICAL 但 Windows 节点
        # resolve 期望 LOGICAL), 直接使用会导致点击位置偏移。
        # 此处只记 warning 不 raise, 因为:
        # 1. 同一 pipeline 跨设备混合是合法场景 (例如 anchor 节点在
        #    ADB 设备 publish, Windows 设备的 click 节点 resolve)
        # 2. 实际坐标系转换应在 device.click 内部处理 (WindowsDevice
        #    会把 logical 转 physical)
        # 但 warning 让 AI 调试时能从日志反推坐标系不匹配的根因。
        if isinstance(var_value, dict):
            var_coord_system = var_value.get("coord_system", "")
            ctx_coord_system = getattr(context, "coord_system", "") or ""
            if (var_coord_system and ctx_coord_system
                    and var_coord_system != ctx_coord_system):
                logger.warning(
                    "resolve_target coord_system mismatch: var %r has "
                    "coord_system=%r but context.coord_system=%r. "
                    "Cross-device coordinate mixing may cause click offset. "
                    "target=%r, resolved=(%d, %d)",
                    var_name, var_coord_system, ctx_coord_system,
                    target, x, y,
                )
                # 把不匹配记到 coord_trace, 让 AI 从 JSONL 反推
                try:
                    context.emit_coord_trace(
                        node_id="resolve_target",
                        step="coord_system_mismatch_warning",
                        raw=var_value,
                        converted=(x, y),
                        formula=f"var_coord_system={var_coord_system} != ctx_coord_system={ctx_coord_system}",
                        coord_system_in=var_coord_system,
                        coord_system_out=ctx_coord_system,
                        extra={"var_name": var_name, "target": str(target)[:120]},
                    )
                except Exception as e:
                    logger.debug("emit_coord_trace failed for var target: %r", e)
    else:
        raise ValueError(f"unsupported target type: {type(target).__name__}={target!r}")

    # Apply offset.
    if offset is not None:
        dx, dy = _resolve_offset(offset)
        x += dx
        y += dy

    # N191 §10.10 决策点 1 (AI 可调试性, 2026-07-27):
    # resolve_target 是动作节点拿识别结果的关键转换点, 必记 trace。
    # AI 调试时通过 grep "resolve_target" 看动作节点拿到的 (x, y) 来自
    # 哪个 target spec + offset, 不需要重跑就能反推点击位置 (D4)。
    try:
        context.emit_coord_trace(
            node_id="resolve_target",
            step="resolve_target",
            raw={"target": str(target)[:120], "offset": str(offset)[:80]},
            converted=(x, y),
            formula=f"resolve_target(target={target!r}, offset={offset!r}) -> ({x}, {y})",
            coord_system_in=getattr(context, "coord_system", "") or "",
            coord_system_out=getattr(context, "coord_system", "") or "",
            extra={"fallback_x": fallback_x, "fallback_y": fallback_y},
        )
    except Exception as e:
        logger.debug("emit_coord_trace failed: %r", e)

    return x, y


def _extract_xy(value: Any, var_name: str) -> tuple[int, int]:
    """Extract (x, y) from a context variable value."""
    if isinstance(value, dict):
        if "x" in value and "y" in value:
            return int(value["x"]), int(value["y"])
        if "center" in value and isinstance(value["center"], dict):
            c = value["center"]
            if "x" in c and "y" in c:
                return int(c["x"]), int(c["y"])
        raise ValueError(f"variable {var_name!r} dict has no x/y or center.x/y: {value!r}")
    if isinstance(value, (list, tuple)):
        if len(value) >= 2:
            return int(value[0]), int(value[1])
        raise ValueError(f"variable {var_name!r} list too short: {value!r}")
    if isinstance(value, (int, float)):
        # Single number — cannot resolve 2D point. Reject.
        raise ValueError(
            f"variable {var_name!r} is scalar {value!r}, cannot resolve to (x, y)"
        )
    raise ValueError(
        f"variable {var_name!r} has unsupported type {type(value).__name__}: {value!r}"
    )


def _resolve_offset(offset: OffsetSpec) -> tuple[int, int]:
    """Resolve an offset spec to (dx, dy)."""
    if isinstance(offset, dict):
        if "x" not in offset or "y" not in offset:
            raise ValueError(f"target_offset dict missing 'x'/'y': {offset!r}")
        return int(offset["x"]), int(offset["y"])
    if isinstance(offset, (list, tuple)):
        if len(offset) < 2:
            raise ValueError(f"target_offset list too short: {offset!r}")
        return int(offset[0]), int(offset[1])
    raise ValueError(
        f"unsupported target_offset type: {type(offset).__name__}={offset!r}"
    )
