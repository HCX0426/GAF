# ruff: noqa: I001
"""check_claimed_rules.py — M2 (2026-08-15) 声称-激活率回执 (post-commit WARN-only).

TEST_SFCAPI verify_activation.py 借鉴: 校验 AI 在 commit message 里声称遵循的
N## 规则是否真有 diff 证据. 防"声称多、证据薄"的形式合规 (反向合规虚高).
N201 (2026-08-16) 增强: 复盘触发闭环 (TEST workflow_rules §3 借鉴) —
rate 排除 unknowable (N/A 语义), 累计有效记录 ≥ 3 且最近 3 条中 ≥ 2 条
< 50% 时输出 🔴 复盘警告并写触发标记, 供 AI 暂停问用户执行复盘模板.
TD-364/s29 (2026-08-17) 增强: 覆盖率盲区补测 — commit message 无声称 N##
但 diff 触及规则文件 (.skills/rules/ .ai-memory/ scripts/hooks/ 等) 时,
追记 NO-CLAIM 行 (verdict=NO-CLAIM, rate=N/A), 使"改规则未声称"的沉默违反
可观测. NO-CLAIM 不参与复盘触发判定 (rate=None 语义沿用 N201).

流程:
1. 读最近 commit message (git log -1 --format=%H%n%B), 提取声称的 N##.
2. 取该 commit 的 diff 路径 + 新增行 (git diff HEAD~1..HEAD).
3. 对每个声称 N##:
   - 有 lesson 且含 diff_keywords → diff 有证据 = positive / 无证据 = no-evidence
   - lesson 有但无 diff_keywords   → unknowable (M3 未回填, 不判负)
   - 无 lesson                     → unknowable
4. effective_rate = positive / (claimed - unknowable); 分母为 0 → N/A
   (不参与复盘判定, 对齐 TEST §3 N/A 跳过语义); 有效记录 < 50% 时 warn.
5. 追记 1 行到 .ai-memory/ops/claimed-activation.md (commit | claimed | positive | rate | verdict).
6. 复盘触发: 累计有效记录 ≥ 3 且最近 3 条有效中 ≥ 2 条 < 50% → 打印 🔴
   复盘警告 + 写 REVIEW_TRIGGERED 标记 (幂等, 同数据快照不重复).
7. 无声称 N## 时: diff 触及规则文件 → NO-CLAIM 行; 否则跳过.

退出码恒 0 (post-commit 只提示不阻断).

Usage:
    python scripts/hooks/check_claimed_rules.py                 # 最近 commit
    python scripts/hooks/check_claimed_rules.py --commit <sha>  # 指定 commit
    python scripts/hooks/check_claimed_rules.py --no-record     # 不写记录文件
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
_LESSONS_DIR = _SCRIPTS_DIR / "lessons"
for _d in (_SCRIPTS_DIR, _LESSONS_DIR):
    if str(_d) not in _sys.path:
        _sys.path.insert(0, str(_d))

import argparse  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from datetime import datetime, UTC  # noqa: E402
from pathlib import Path  # noqa: E402

from match_lessons_by_diff import (  # noqa: E402
    collect_diff,
    load_lessons,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_RECORD = REPO_ROOT / ".ai-memory" / "ops" / "claimed-activation.md"

# 规则影响文件前缀 (TD-364/s29 2026-08-17): commit 触及这些路径但 message
# 未声称 N## → 追记 NO-CLAIM 行, 补 M2 覆盖率盲区 ("沉默违反"可观测).
RULE_DIRS = (
    ".skills/rules/",
    ".skills/skills/",
    ".ai-memory/",
    "scripts/hooks/",
    "scripts/lessons/",
    "docs/specs/",  # spec 是 AI 工作流承载体 (TD-342): 改 spec 未声称也需观测
    ".pre-commit-config.yaml",
)
# 排除 ops/ 运营记录输出目录 (claimed-activation / why-skipped 等是审计脚本产物,
# 不是规则输入; 否则记录 NO-CLAIM 行的 commit 必然改 OPS_RECORD → 自记录循环).
RULE_DIRS_EXCLUDE = (".ai-memory/ops/",)

# 行为/合规/环境/文档流程类规则: AI 遵守但 diff 无代码证据 (如双调试视角 N192 /
# 诊断触发 N204 / 任务归属 N193 / 三维根因 N182 / 决策自决 N109 / 环境归一 N199 等).
# 这类声称不应拖低激活率, 视作 N/A 豁免 (与 unknowable 同类, 不计入 no_evidence,
# 不进分母). 列表与 failure-modes.md Active 段行为类条目对齐.
# TD-382 (2026-08-24): 从 {N192,N204,N193} 扩展覆盖复盘中确认误判的行为/合规/环境/
# 流程类规则 (N182/N185/N109/N199/N188/N190/N205/N140/N167/N179/N176/N108).
# 注意: 有真实代码 diff 语义的规则 (如 N191 schema / N112 字段同步 / N152 分页 /
# N202 拆文件清单) 必须保持代码类, 不得加入本集合 (否则 M2 对其失去 diff 监督, 见
# test_check_claimed_rules.py::test_verify_claims_code_rule_no_evidence).
BEHAVIORAL_N = {
    "N108", "N109", "N140", "N167", "N176", "N182", "N185",
    "N188", "N190", "N199", "N205",
    "N192", "N204", "N193",
}

POSITIVE_RATE_WARN = 0.5  # < 50% → warn (TEST v3.4 主指标)
REVIEW_MIN_RECORDS = 3  # 累计有效记录 ≥ 3 才可触发复盘 (TEST §3 降级版)
REVIEW_LOW_IN_LAST3 = 2  # 最近 3 条有效中 ≥ 2 条 < 50% → 触发复盘
REVIEW_MARKER = "> 🔴 REVIEW_TRIGGERED"  # 复盘触发标记行前缀


def _git(*args: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        return r.stdout if r.returncode == 0 else ""
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return ""


def get_last_commit(commit: str | None) -> tuple[str, str]:
    """Return (hash, message) for the given commit (default: HEAD)."""
    ref = commit or "HEAD"
    out = _git("log", "-1", "--format=%H%n%B", ref)
    lines = out.splitlines()
    if not lines:
        return "", ""
    return lines[0], "\n".join(lines[1:]).strip()


def extract_claimed_ns(message: str) -> list[str]:
    """从 commit message 提取声称的 N## (去重, 保序)."""
    seen: list[str] = []
    for n in re.findall(r"\bN\d{2,4}\b", message):
        if n not in seen:
            seen.append(n)
    return seen


def _lesson_n_map(lessons: list[dict]) -> dict[str, list[dict]]:
    """N## → lessons 列表 (从文件名 N<num> 前缀提取)."""
    m: dict[str, list[dict]] = {}
    for lesson in lessons:
        mm = re.match(r"^(N\d+)", lesson["path"].split("/")[-1])
        if mm:
            m.setdefault(mm.group(1), []).append(lesson)
    return m


def verify_claims(
    claimed: list[str], lessons: list[dict], changed_paths: list[str],
    tokens: set[str], added_lines: list[str],
) -> tuple[int, int, int, int, list[str], list[str]]:
    """返回 (positive, no_evidence, unknowable, behavioral, positive_ns, no_evidence_ns)."""
    n_map = _lesson_n_map(lessons)
    positive: list[str] = []
    no_evidence: list[str] = []
    unknowable: list[str] = []
    behavioral: list[str] = []
    for n in claimed:
        if n in BEHAVIORAL_N:          # 行为类豁免: 不进分母, 不计 no_evidence
            behavioral.append(n)
            continue
        candidates = n_map.get(n, [])
        if not candidates:
            unknowable.append(n)
            continue
        with_kw = [c for c in candidates if c["diff_keywords"]]
        if not with_kw:
            unknowable.append(n)
            continue
        hit = False
        for c in with_kw:
            for kw in c["diff_keywords"]:
                if (
                    any(kw in p for p in changed_paths)
                    or kw in tokens
                    or any(kw in line for line in added_lines)
                ):
                    hit = True
                    break
            if hit:
                break
        # v9.2 Spec C-2 (2026-08-22): 引用性提及豁免 — N## 字面出现在 diff 新增行
        # 或路径中 = 该 commit 真实改动了与此 N## 相关的内容 (如修 failure-modes
        # 断链时正文提到 N151), 不应因 lesson diff_keywords 未回填而判 no-evidence.
        # 这解耦了"文档词汇"与"声称": 有 diff 痕迹的提及是内容关联, 无痕迹的
        # 裸声称仍照常核验.
        if not hit:
            hit = (
                any(re.search(rf"\b{re.escape(n)}\b", ln) for ln in added_lines)
                or any(n in p for p in changed_paths)
            )
        (positive if hit else no_evidence).append(n)
    return (
        len(positive), len(no_evidence), len(unknowable),
        len(behavioral), positive, no_evidence,
    )


def _write_record(
    commit_hash: str, claimed: list[str], positive: list[str],
    no_evidence: list[str], rate: float | None,
) -> None:
    """追记 1 行到 claimed-activation.md (幂等: 同 commit 不重复).

    rate=None → N/A 语义 (分母全为 unknowable, 不参与复盘判定, 对齐 TEST §3).
    """
    if not commit_hash:
        return
    OPS_RECORD.parent.mkdir(parents=True, exist_ok=True)
    header = "| timestamp | commit | claimed | positive | no-evidence | rate | verdict |"
    sep = "|---|---|---|---|---|---|---|"
    short = commit_hash[:8]
    if OPS_RECORD.exists() and short in OPS_RECORD.read_text(encoding="utf-8"):
        return  # 幂等: 该 commit 已记录
    if rate is None:
        verdict = "N/A"
        rate_str = "N/A"
    else:
        verdict = "OK" if rate >= POSITIVE_RATE_WARN else "LOW"
        rate_str = f"{rate:.0%}"
    row = (
        f"| {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} "
        f"| `{short}` | {','.join(claimed) or '-'} "
        f"| {','.join(positive) or '-'} "
        f"| {','.join(no_evidence) or '-'} "
        f"| {rate_str} | {verdict} |"
    )
    if not OPS_RECORD.exists():
        OPS_RECORD.write_text(
            f"# Claimed-Rules Activation Receipt (M2, 2026-08-15)\n\n"
            f"> post-commit 自动记录: commit message 声称的 N## 规则 vs diff 证据.\n"
            f"> positive = diff 有 diff_keywords 证据; no-evidence = 声称但无证据;\n"
            f"> N/A = 分母全为 unknowable (无 lesson / 无 diff_keywords 回填),\n"
            f"> 不参与复盘判定 (N201). 只提示不阻断.\n\n"
            f"{header}\n{sep}\n{row}\n",
            encoding="utf-8",
        )
    else:
        text = OPS_RECORD.read_text(encoding="utf-8")
        if header not in text:
            text = f"{text.rstrip()}\n\n{header}\n{sep}\n"
        OPS_RECORD.write_text(f"{text.rstrip()}\n{row}\n", encoding="utf-8")


def _rule_files(changed_paths: list[str]) -> list[str]:
    """过滤出触及规则影响文件的路径 (排除 OPS_RECORD 自身)."""
    return [
        p for p in changed_paths
        if any(p.startswith(d) for d in RULE_DIRS)
        and not any(p == e or p.startswith(e) for e in RULE_DIRS_EXCLUDE)
    ]


def _write_no_claim_record(commit_hash: str, rule_files: list[str]) -> bool:
    """追记 NO-CLAIM 行 (幂等: 同 commit 不重复). 返回是否新写."""
    if not commit_hash or not rule_files:
        return False
    OPS_RECORD.parent.mkdir(parents=True, exist_ok=True)
    short = commit_hash[:8]
    if OPS_RECORD.exists() and short in OPS_RECORD.read_text(encoding="utf-8"):
        return False  # 幂等: 该 commit 已有记录 (claimed 或 NO-CLAIM)
    marker = "NO-CLAIM"
    files = "; ".join(rule_files[:5])
    if len(rule_files) > 5:
        files += f" (+{len(rule_files) - 5} more)"
    row = (
        f"| {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} "
        f"| `{short}` | - | - | {files} | N/A | {marker} |"
    )
    header = "| timestamp | commit | claimed | positive | no-evidence | rate | verdict |"
    sep = "|---|---|---|---|---|---|---|"
    if not OPS_RECORD.exists():
        OPS_RECORD.write_text(
            f"# Claimed-Rules Activation Receipt (M2, 2026-08-15)\n\n"
            f"> post-commit 自动记录: commit message 声称的 N## 规则 vs diff 证据.\n"
            f"> positive = diff 有 diff_keywords 证据; no-evidence = 声称但无证据;\n"
            f"> NO-CLAIM = 改规则文件但未声称 N## (TD-364 覆盖率盲区补测);\n"
            f"> N/A = 分母全为 unknowable (无 lesson / 无 diff_keywords 回填),\n"
            f"> 不参与复盘判定 (N201). 只提示不阻断.\n\n"
            f"{header}\n{sep}\n{row}\n",
            encoding="utf-8",
        )
        return True
    text = OPS_RECORD.read_text(encoding="utf-8")
    if header not in text:
        text = f"{text.rstrip()}\n\n{header}\n{sep}\n"
    OPS_RECORD.write_text(f"{text.rstrip()}\n{row}\n", encoding="utf-8")
    return True


def load_records(record_path: Path | None = None) -> list[dict]:
    """解析 claimed-activation.md 记录行.

    兼容 6 列 (无 no-evidence) / 7 列两种格式; N/A 行 rate=None (不参与复盘判定).
    """
    path = record_path or OPS_RECORD
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("| timestamp"):
            continue
        cells = [p.strip() for p in line.strip("|").split("|")]
        if len(cells) < 6 or all(p == "---" for p in cells):
            continue
        commit = cells[1].strip("`")
        rate_raw = cells[5] if len(cells) >= 7 else cells[4]
        rows.append({
            "commit": commit,
            "claimed": cells[2],
            "positive": cells[3],
            "no_evidence": cells[4] if len(cells) >= 7 else "-",
            "rate": None if rate_raw in ("N/A", "-") else float(rate_raw.strip("%")) / 100,
        })
    return rows


def check_review_trigger(
    records: list[dict],
    min_records: int = REVIEW_MIN_RECORDS,
    low_in_last3: int = REVIEW_LOW_IN_LAST3,
) -> tuple[bool, list[dict]]:
    """复盘触发判定 (TEST workflow_rules §3 降级版).

    N/A 记录 (rate=None) 不参与判定——既不算 < 50% 也不算 ≥ 50%, 从回溯中跳过.
    触发 = 累计有效记录 ≥ 3 且 最近 3 条有效中 ≥ 2 条 < 50%.
    返回 (triggered, 最近 3 条有效记录).
    """
    valid = [r for r in records if r["rate"] is not None]
    if len(valid) < min_records:
        return False, []
    last3 = valid[-3:]
    low = sum(1 for r in last3 if r["rate"] < POSITIVE_RATE_WARN)
    return (low >= low_in_last3), last3


REVIEW_CLOSURE_MARK = "📋 复盘"


def check_unclosed_review(record_path: Path | None = None) -> int:
    """TD-376 (2026-08-20): REVIEW_TRIGGERED 未闭环强制检查 (pre-commit).

    读 claimed-activation.md, 找最后一个 REVIEW_TRIGGERED 标记行; 若该行之后
    无 `📋 复盘` 写回 → 输出 🔴 警告并返回 1 (阻塞 commit, 强制 AI 复盘闭环).
    无标记行 / 已闭环 → 返回 0. 幂等: 复盘写回后标记自然解除.
    """
    path = record_path or OPS_RECORD
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    markers = [ln for ln in text.splitlines() if ln.strip().startswith(REVIEW_MARKER)]
    if not markers:
        return 0
    last_marker = markers[-1]
    after = text.split(last_marker, 1)[1]
    if REVIEW_CLOSURE_MARK in after:
        return 0
    # TD-383 (2026-08-22): 未写回复盘时重估触发条件是否仍成立 — 仅当最近有效
    # 记录中 LOW 数仍达阈值才阻塞; 陈旧标记 (触发条件已不成立) 视为自然闭环,
    # 防"为解锁而形式化补复盘" (N189 治理形式化风险). 真实触发仍阻塞不豁免.
    triggered_now, last3 = check_review_trigger(load_records(path))
    if not triggered_now:
        print("ℹ️  [M2] REVIEW_TRIGGERED 标记未写回复盘, 但当前有效记录已不满足"
              "触发条件 → 陈旧标记自然闭环, 不阻塞")
        return 0
    print(f"🔴 [M2] REVIEW_TRIGGERED 未闭环 (TD-376): 最新标记行如下, 其后无 📋 复盘写回")
    print(f"    {last_marker.strip()}")
    print(f"    → 必须按复盘模板 Q1-Q4 执行并写回 .ai-memory/ops/claimed-activation.md")
    print(f"    → 历史复盘示例: 2026-08-16 a8e75db3 触发后的 📋 复盘块")
    return 1


def _write_review_trigger(commit_hash: str, last3: list[dict]) -> bool:
    """追加复盘触发标记行 (幂等: 同数据快照不重复). 返回是否新写."""
    if not commit_hash or not last3:
        return False
    OPS_RECORD.parent.mkdir(parents=True, exist_ok=True)
    short = commit_hash[:8]
    snapshot = ",".join(r["commit"][:8] for r in last3)
    marker = f"{REVIEW_MARKER} (snapshot {snapshot}, trigger {short})"
    text = OPS_RECORD.read_text(encoding="utf-8") if OPS_RECORD.exists() else ""
    if marker in text:
        return False  # 同数据快照已触发过, 不重复
    with OPS_RECORD.open("a", encoding="utf-8") as f:
        f.write(f"{marker}\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="M2: 声称-激活率回执 (commit message N## vs diff 证据)",
    )
    parser.add_argument("--commit", default=None, help="指定 commit (默认 HEAD)")
    parser.add_argument("--no-record", action="store_true", help="不写记录文件")
    args = parser.parse_args(argv)

    commit_hash, message = get_last_commit(args.commit)
    claimed = extract_claimed_ns(message)
    if not claimed:
        # TD-364/s29: 无声称时补测规则文件变更盲区 — commit 改了规则层但未声称
        base = f"{args.commit}~1" if args.commit else "HEAD~1"
        head = args.commit or "HEAD"
        changed_paths, _, _ = collect_diff(None, base, head)
        rule_files = _rule_files(changed_paths)
        if rule_files:
            print(f"ℹ️  [M2] commit message 无声称 N##, 但触及规则文件 "
                  f"{len(rule_files)} 个: {', '.join(rule_files[:5])}")
            if not args.no_record and _write_no_claim_record(commit_hash, rule_files):
                print(f"  ⚠️  NO-CLAIM 已记录到 {OPS_RECORD.name} (覆盖率盲区补测, TD-364)")
        else:
            print("ℹ️  [M2] commit message 无声称 N##, 跳过")
        return 0

    base = f"{args.commit}~1" if args.commit else "HEAD~1"
    head = args.commit or "HEAD"
    changed_paths, tokens, added_lines = collect_diff(None, base, head)
    lessons = load_lessons(REPO_ROOT / ".ai-memory" / "lessons")
    positive_n, no_ev_n, unk_n, behav_n, positive, no_evidence = verify_claims(
        claimed, lessons, changed_paths, tokens, added_lines,
    )
    total = len(claimed)
    effective = total - unk_n - behav_n  # 分母排除 unknowable + 行为类豁免
    rate = positive_n / effective if effective else None

    rate_str = f"{rate:.0%}" if rate is not None else "N/A"
    print(f"[M2] commit {commit_hash[:8]} 声称 {total} 条 N##: "
          f"positive={positive_n} no-evidence={no_ev_n} "
          f"unknowable={unk_n} behavioral={behav_n} "
          f"有效激活率={rate_str}")
    if no_evidence:
        print(f"  ⚠️  声称但无 diff 证据: {', '.join(no_evidence)}")
    if positive:
        print(f"  ✅ 有 diff 证据: {', '.join(positive)}")
    if rate is not None and rate < POSITIVE_RATE_WARN:
        print(f"  🔴 有效激活率 < {POSITIVE_RATE_WARN:.0%}, 疑似'声称多、证据薄'")

    if not args.no_record:
        _write_record(commit_hash, claimed, positive, no_evidence, rate)

    triggered, last3 = check_review_trigger(load_records())
    if triggered:
        rates = " / ".join(
            f"{r['commit'][:8]} {r['rate']:.0%}" for r in last3
        )
        print(f"  🔴 复盘触发: 累计有效记录 ≥ {REVIEW_MIN_RECORDS} 且最近 3 条中 "
              f"≥ {REVIEW_LOW_IN_LAST3} 条 < {POSITIVE_RATE_WARN:.0%} ({rates})")
        if not args.no_record and _write_review_trigger(commit_hash, last3):
            print(f"  ⚠️  复盘标记已写入 {OPS_RECORD.name}, 下次任务开工时按复盘模板执行 (Q1-Q4)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
