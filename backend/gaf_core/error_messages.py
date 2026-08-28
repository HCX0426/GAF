"""Node-level error code → user-facing message mapping (N192 视角 B).

Purpose:
    Backend receives ``NodeErrorCode`` strings from the agent (via
    ``AutoResult.error_code``) and needs to convert them to a message the
    *user* can understand — not the raw exception text or the error code
    constant name.  This dict is the single source of truth for that mapping.

    Why a separate file (not inline in error_codes.py):
    - error_codes.py is shared between backend and agent (imports in
      agent/src/core/error_codes.py) — user-facing Chinese text does not
      belong on the agent side.
    - Keeping the mapping here makes it easy to diff / extend / i18n later
      (when the frontend ever switches away from hard-coded Chinese UI).

Hard constraints (N192 双视角):
    - B1 错误提示归一: 原始异常 ``KeyError('steps')`` 绝不直接透传到前端,
      必须映射成"任务定义缺少 steps 字段, 请在任务编辑器中补全节点".
    - B2 错误码映射: 同一 ``error_code`` 返回一致的 user_message.
    - B7 复现路径: user_message 尽量包含"用户下一步该做什么".
"""

from __future__ import annotations

from gaf_core.error_codes import NodeErrorCode

# {error_code: user_message}
# 中文文案是当前 GAF 前端的默认语言 (zh-CN); 未来加 en/ja 时可
# 改为 locale-dict 结构, 此处先保持扁平以便快速查阅.
ERROR_USER_MESSAGES: dict[str, str] = {
    # --- 识别类 ---
    NodeErrorCode.NO_MATCH: "画面上未识别到目标图案, 请检查模板图片是否清晰或降低匹配阈值",
    NodeErrorCode.LOW_CONFIDENCE: "目标匹配置信度过低, 建议更换模板或提高画面对比度",
    NodeErrorCode.OCR_EMPTY: "OCR 未识别到任何文字, 请检查文字区域是否清晰可见",
    NodeErrorCode.COLOR_NOT_FOUND: "未检测到指定颜色, 请确认颜色值是否正确或画面是否已刷新",
    # --- 竞态类 ---
    NodeErrorCode.SCREEN_UNCHANGED: "点击后画面没有变化, 目标控件可能不可点击或已失效",
    NodeErrorCode.SCREEN_TIMEOUT: "等待画面变化超时, 操作可能未生效, 请重试或增加等待时间",
    # --- 设备类 ---
    NodeErrorCode.DEVICE_ERROR: "设备操作失败, 请检查设备连接状态",
    NodeErrorCode.DEVICE_DISCONNECTED: "设备已断开连接, 请重新连接后再试",
    # --- 输入类 ---
    NodeErrorCode.COORD_INVALID: "坐标解析失败, 请确认节点输入的坐标值合法",
    NodeErrorCode.TARGET_NOT_FOUND: "引用的目标变量不存在, 请检查前置节点是否已正确输出",
    NodeErrorCode.PARAM_INVALID: "节点参数不合法 (如 clicks < 1), 请在任务编辑器中修正",
    # --- 验证类 ---
    NodeErrorCode.PRE_VERIFY_FAILED: "执行前验证失败, 前置条件未满足, 请检查前置节点状态",
    NodeErrorCode.POST_VERIFY_FAILED: "执行后验证失败, 操作结果未达到预期, 请检查后置验证条件",
    # --- 超时/中断 ---
    NodeErrorCode.TIMEOUT: "节点执行超时, 建议增加超时时间或检查设备响应速度",
    NodeErrorCode.INTERRUPTED: "执行已被外部中断",
    # --- 通用 ---
    NodeErrorCode.UNKNOWN: "节点执行发生未知错误, 请联系开发者查看详细日志",
}


def get_user_message(error_code: str | None, default: str = "") -> str:
    """Return user-facing message for a node error code.

    N192-B1 兜底: 任意未知 error_code 返回空串, 由调用方决定是否展示
    默认文案 (通常是"节点执行失败, 请查看日志").
    """
    if not error_code:
        return default or "节点执行失败"
    return ERROR_USER_MESSAGES.get(error_code, default or "节点执行失败")
