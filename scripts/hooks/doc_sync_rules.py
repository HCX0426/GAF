"""doc_sync_rules.py — TD-325 (spec-87) 代码-文档因果绑定规则表.

数据驱动的规则表，定义 8 类代码变更场景需同步的文档。
新增规则只需在 ``RULES`` 列表加一行 ``DocSyncRule`` 即可，
无需修改 ``check_doc_code_sync.py`` 主逻辑。

规则类型
--------
1. **路径+内容规则** (R1/R2/R5/R7): ``trigger_pattern`` fnmatch glob 匹配
   文件路径 + ``content_keywords`` 扫描 diff 内容 → 检查 ``required_docs`` 同步状态
2. **状态信号规则** (R3/R4/R6): 基于 git status letter (A/R/D) 触发,
   不扫内容、不检查文档同步，仅打印提示
3. **文档自同步规则** (R8): docs/**/*.md modified → 强制 doc_last_updated 字段同步更新
   (spec §9.3 扩展点 1, P2 阶段新增)

Severity 分级
-------------
- ``hard``  : 硬阻断，exit 1 (除非 commit message 含 [skip-doc-sync])
- ``warn``  : 警告，exit 0 (N167 反思阶段强制确认)
- ``info``  : 仅信息提示，不计入 fail/warn

设计参考: ``scripts/hooks/check_path_consistency.py`` (KNOWN_SCRIPTS 数据驱动)
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass


@dataclass(frozen=True)
class DocSyncRule:
    """单条代码-文档同步规则。

    Fields
    ------
    id : 规则编号 (R1..R7)
    description : 人类可读说明
    trigger_pattern : fnmatch glob; None = 不按路径匹配
    content_keywords : diff 内容必须命中至少一个关键字才触发;
                       空 tuple = 不扫内容, 任何路径命中即触发
    required_docs : 需同步的文档路径 (repo-relative);
                    空 tuple = 不检查文档同步 (仅状态信号规则)
    severity : "hard" | "warn" | "info"
    status_filter : None=任意; "A"=仅新增; "RD"=rename 或 delete
    """

    id: str
    description: str
    trigger_pattern: str | None
    content_keywords: tuple[str, ...]
    required_docs: tuple[str, ...]
    severity: str
    status_filter: str | None = None


# 7 条规则 — 顺序决定输出顺序
RULES: list[DocSyncRule] = [
    DocSyncRule(
        id="R1",
        description="backend URL 路由变更 → API 契约文档",
        trigger_pattern="backend/*/urls.py",
        content_keywords=("path(", "re_path(", "urlpatterns"),
        required_docs=("docs/standards/api-contract.md",),
        severity="hard",
    ),
    DocSyncRule(
        id="R2",
        description="backend model 字段变更 → 后端规范文档",
        trigger_pattern="backend/*/models.py",
        content_keywords=(
            "models.CharField",
            "models.TextField",
            "models.JSONField",
            "models.ForeignKey",
            "models.OneToOneField",
            "models.ManyToManyField",
            "models.BooleanField",
            "models.IntegerField",
            "models.DateTimeField",
            "Field(",
        ),
        required_docs=("docs/standards/backend-conventions.md",),
        severity="hard",
    ),
    DocSyncRule(
        id="R3",
        description="新增 backend app 目录 → 设计文档",
        trigger_pattern="backend/*/apps.py",  # Django app 标识文件
        content_keywords=(),  # 状态信号规则，不扫内容
        required_docs=("docs/architecture/", "docs/business/"),  # 双线索目录前缀，仅提示 (P0 重构后)
        severity="warn",
        status_filter="A",
    ),
    DocSyncRule(
        id="R4",
        description="模块重命名/删除 → 全仓库引用同步",
        trigger_pattern=None,  # 不按路径匹配，纯状态信号
        content_keywords=(),
        required_docs=(),  # 不检查具体文档，提示人工 grep
        severity="hard",
        status_filter="RD",
    ),
    DocSyncRule(
        id="R5",
        description="前端 API 客户端变更 → API 契约文档",
        trigger_pattern="frontend/src/api/*.ts",
        content_keywords=("fetch(", "axios", "request(", "http.", "url:", "endpoint:"),
        required_docs=("docs/standards/api-contract.md",),
        severity="warn",
    ),
    DocSyncRule(
        id="R6",
        description="新增 spec 文件 → sync_spec_index 自动同步",
        trigger_pattern="docs/specs/legacy-trae/*.md",
        content_keywords=(),  # 新增即触发
        required_docs=(),  # governance batch 已有 sync_spec_index 检查
        severity="info",
        status_filter="A",
    ),
    DocSyncRule(
        id="R7",
        description="backend settings 变更 → 部署设计文档",
        trigger_pattern="backend/config/settings/*.py",
        content_keywords=("INSTALLED_APPS", "MIDDLEWARE", "CELERY", "DATABASES", "CACHES", "REST_FRAMEWORK"),
        required_docs=("docs/architecture/desktop/deployment-design.md",),  # P0 重构后路径
        severity="warn",
    ),
]


def match_rules(
    filepath: str,
    status: str = "M",
) -> list[DocSyncRule]:
    """返回命中的规则列表 (按 RULES 顺序)。

    Parameters
    ----------
    filepath : repo-relative 文件路径 (forward slash)
    status : git status letter. M=modified, A=added, D=deleted,
             R=rename (status 可能是 R100 等带分数的形式, 取首字母)

    Returns
    -------
    list[DocSyncRule]
        命中的规则。同一文件可能命中多条 (例如 backend/accounts/urls.py
        既匹配 R1 路径模式, 也可能因 status='M' 触发其他状态规则)。
    """
    status_letter = status[0].upper() if status else "M"
    hits: list[DocSyncRule] = []
    for rule in RULES:
        # 状态过滤
        if rule.status_filter is not None:
            if status_letter not in rule.status_filter:
                continue
            # 状态信号规则: 路径 pattern 仍要匹配 (R3/R6), R4 路径 pattern=None 跳过
            if rule.trigger_pattern is None:
                hits.append(rule)
                continue
            if fnmatch.fnmatch(filepath, rule.trigger_pattern):
                hits.append(rule)
                continue
            # 状态匹配但路径不匹配 → 不命中
            continue

        # 路径+内容规则: 路径必须匹配
        if rule.trigger_pattern is None:
            continue
        if not fnmatch.fnmatch(filepath, rule.trigger_pattern):
            continue
        # 路径匹配, 命中 (内容关键字检查由 check_doc_code_sync._scan_diff_content 完成)
        hits.append(rule)
    return hits


def is_hard_rule(rule: DocSyncRule) -> bool:
    """True if rule severity is 'hard'."""
    return rule.severity == "hard"


def is_warn_rule(rule: DocSyncRule) -> bool:
    """True if rule severity is 'warn'."""
    return rule.severity == "warn"
