"""symptom_synonyms.py — GAF symptom taxonomy and synonym dictionary.

This module is the single source of truth for symptom category synonyms
used by `sync_ai_memory.py --query`. It implements the "AI 主动扩展入口"
mechanism (N89 fix, v8.3.1 O5 optimization).

Dictionary format:
    SYNONYMS = {
        "<category[:sub[:value]]>": ["<synonym_1>", "<synonym_2>", ...],
        ...
    }

Rules:
- Category keys are lowercase English (e.g. "popup:agent:duplicate").
- Each entry must have at least 2 synonyms (1+ Chinese, 1+ English).
- New entries can be appended by AI agents at runtime via
  `register_category()` — see M0.B.5 below.

AI extension entry-point (N89 / O5):
    When a new lesson introduces a symptom category not in SYNONYMS,
    the AI agent should call `register_category()` with at least 2
    synonyms (one Chinese, one English) so subsequent --query calls
    can find it. See Appendix E §E.5.
"""
from __future__ import annotations

import threading
from typing import Dict, List

# The base dictionary, declared in spec.md Appendix E §E.2.
# 11 entries seeded at M0 bootstrap; AI extensions add more over time.
SYNONYMS: Dict[str, List[str]] = {
    # Popups
    "popup": ["弹窗", "多开", "重复启动", "duplicate", "spawn"],
    "popup:agent": ["agent-popup", "agent 弹窗", "agent 重复"],
    "popup:agent:duplicate": ["父子进程", "Django runserver 弹窗"],

    # API
    "api": ["API", "接口", "endpoint", "路由"],
    "api:404": ["404", "not found", "找不到"],
    "api:404:task": ["任务创建 404", "POST tasks 404"],

    # Agent
    "agent": ["Agent", "代理", "client"],
    "agent:message": ["消息", "message", "frame", "WebSocket"],
    "agent:message:frame": ["消息帧", "frame 错误", "ws 协议"],
    "agent:capability": ["能力", "capability", "版本不匹配"],
    "agent:capability:mismatch": ["能力不匹配", "capability 缺失"],

    # Pipeline
    "pipeline": ["Pipeline", "流水线", "工作流"],
    "pipeline:stuck": ["卡住", "stuck", "永远运行", "timeout"],
    "pipeline:stuck:running": ["节点 running", "状态不更新"],

    # Spec
    "spec": ["规范", "spec", "文档", "documentation"],
    "spec:overengineering": ["过度设计", "scope creep", "spec 膨胀", "meta 套 meta"],

    # v8.3.1 dynamic extensions
    "workflow:pre-commit": ["pre-commit", "hook", "提交拦截", "gaf-commit"],
    "workflow:pre-commit:hook-failed": ["hook 失败", "❌ hook", "修复命令", "N91 映射表"],
    "decision-tree:drift": ["决策树漂移", "副本不一致", "4 份 SKILL.md", "sync_decision_tree"],

    # 🆕 v8.4 M0.N 收尾: commit / hook 透传 + auto-maintained 文件回滚
    "workflow:commit": ["commit", "提交", "git commit"],
    "workflow:commit:bypass": ["--no-verify", "bypass", "绕过 hook", "GAF_BYPASS_REASON"],
    "workflow:commit:bypass-rollback": [
        "gaf-commit 透传 bug", "hook 误回滚", "MM 状态",
        "files were modified by this hook", "n105",
        "commit 没真发生", "audit log 错觉", "sync_ai_memory 误覆盖",
    ],

    # 🆕 v9.0 Task B.4: concurrency topic (N116)
    "concurrency": ["并发", "concurrent", "race condition", "sync race", "R-M-W", "sync_lock"],
}

# Re-entrant lock protecting SYNONYMS from concurrent extension by multiple AIs.
_LOCK = threading.RLock()


def get_synonyms(category: str) -> List[str]:
    """Return the synonym list for a category, or [] if unknown.

    Performs an exact key match. Prefix matches (e.g. "popup" matches
    "popup:agent") are handled by `expand_query()` instead, which
    walks the dictionary in both directions.
    """
    return list(SYNONYMS.get(category, []))


def get_all_categories() -> List[str]:
    """Return all registered category keys, sorted alphabetically."""
    with _LOCK:
        return sorted(SYNONYMS.keys())


def register_category(category: str, synonyms: List[str]) -> bool:
    """Register a new symptom category with at least 2 synonyms.

    Implements the "AI 主动扩展入口" mechanism (Appendix E §E.5, N89 fix).
    Returns True if the category was added, False if it was rejected
    (insufficient synonyms, empty keys, or invalid characters).

    Rules:
    - `category` must be non-empty and lowercase.
    - `synonyms` must contain at least 2 non-empty strings.
    - The combined synonyms must include at least one CJK character
      (Chinese) AND at least one ASCII letter, ensuring bilingual
      coverage. This is the "1+ Chinese + 1+ English" rule.
    - Re-registering an existing category is allowed and updates the
      synonym list (idempotent, useful when AI refines terminology).
    """
    if not category or not isinstance(category, str):
        return False
    if not category.replace(":", "").replace("_", "").replace("-", "").isalnum():
        return False
    if category != category.lower():
        return False
    if not synonyms or len(synonyms) < 2:
        return False
    cleaned = [s.strip() for s in synonyms if s and s.strip()]
    if len(cleaned) < 2:
        return False
    has_cjk = any(any("\u4e00" <= ch <= "\u9fff" for ch in s) for s in cleaned)
    has_ascii = any(any(ch.isascii() and ch.isalpha() for ch in s) for s in cleaned)
    if not (has_cjk and has_ascii):
        return False
    with _LOCK:
        SYNONYMS[category] = cleaned
    return True


def _has_cjk(text: str) -> bool:
    """Return True if `text` contains any CJK (Chinese) character."""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _tokenize(text: str) -> List[str]:
    """Split a query into tokens.

    Chinese characters are split one-by-one (each char is a token),
    while ASCII runs are kept together as a single token. Punctuation
    and whitespace are dropped.
    """
    tokens: List[str] = []
    buf: List[str] = []
    for ch in text:
        if _has_cjk(ch):
            if buf:
                tokens.append("".join(buf))
                buf = []
            tokens.append(ch)
        elif ch.isalnum() and ch.isascii():
            buf.append(ch)
        else:
            if buf:
                tokens.append("".join(buf))
                buf = []
    if buf:
        tokens.append("".join(buf))
    return [t for t in tokens if t]


def expand_query(query: str) -> List[str]:
    """Expand a user query into a set of searchable keywords.

    Given a query like "弹窗" or "agent popup", return a list of
    keywords that should be matched against lesson symptom fields.
    The expansion walks the SYNONYMS dictionary in both directions:

    1. If a token exactly matches a category key (or a substring of one),
       add the entire category key + all its synonyms.
    2. If a token matches any synonym, add the parent category key +
       all of its other synonyms.
    3. Tokens that don't match anything in the dictionary are kept
       as-is so that bare searches still work.

    Duplicate keywords are removed while preserving first-seen order.
    """
    tokens = _tokenize(query)
    seen: set = set()
    out: List[str] = []

    def _add(keyword: str) -> None:
        if keyword and keyword not in seen:
            seen.add(keyword)
            out.append(keyword)

    with _LOCK:
        for token in tokens:
            matched = False
            for category, syns in SYNONYMS.items():
                token_lower = token.lower()
                # 1. Token is the category itself, a prefix, or a substring.
                if (
                    category == token
                    or category.startswith(token + ":")
                    or token_lower in category
                ):
                    matched = True
                    _add(category)
                    for s in syns:
                        _add(s)
                    continue
                # 2. Token appears in any synonym (exact, substring, or superstring).
                for s in syns:
                    s_lower = s.lower()
                    if token_lower == s_lower or token_lower in s_lower or s_lower in token_lower:
                        matched = True
                        _add(category)
                        for s2 in syns:
                            _add(s2)
                        break
            if not matched:
                _add(token)
    return out
