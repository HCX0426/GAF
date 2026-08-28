"""test_check_claimed_rules.py — M2 (2026-08-15) 声称-激活率回执测试.

Covers:
1. extract_claimed_ns: 从 message 提取 N##, 去重保序
2. verify_claims: positive / no-evidence / unknowable 三分
3. _write_record: 幂等 (同 commit 不重复) + 首次建表 + N/A 语义
4. load_records: 兼容 6/7 列格式 + N/A 解析
5. check_review_trigger: 复盘触发判定 (TEST §3 降级版, N/A 跳过)
6. _write_review_trigger: 幂等标记
7. main(): 无声称 → 0
"""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap scripts/ import
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
HOOKS_DIR = SCRIPTS_DIR / "hooks"
for d in (SCRIPTS_DIR, HOOKS_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

import check_claimed_rules as c  # noqa: E402
import pytest  # noqa: E402

pytestmark = pytest.mark.unit


def test_extract_claimed_ns_dedup_order():
    msg = "feat(x): 修 N151 + N157 — N150\n\nbody N151 again N167 N167\n"
    assert c.extract_claimed_ns(msg) == ["N151", "N157", "N150", "N167"]


def test_extract_claimed_ns_none():
    assert c.extract_claimed_ns("feat(x): 无规则引用") == []


def _lesson(path: str, kws: list[str]) -> dict:
    return {
        "path": path,
        "diff_keywords": [k.lower() for k in kws],
        "related_files": [],
    }


def test_verify_claims_positive_noevidence_unknowable():
    lessons = [
        _lesson("N151-arch.md", ["architecture-first"]),
        _lesson("N157-doc.md", ["fabrication"]),
    ]
    pos, no_ev, unk, behav, pos_ns, no_ev_ns = c.verify_claims(
        ["N151", "N157", "N197", "N999"],
        lessons,
        ["docs/x.md"],
        set(),
        ["# architecture-first decision"],
    )
    assert pos == 1 and no_ev == 1 and unk == 2
    assert pos_ns == ["N151"]
    assert no_ev_ns == ["N157"]


def test_verify_claims_lesson_without_keywords_unknowable():
    lessons = [_lesson("N150-precommit.md", [])]
    pos, no_ev, unk, behav, _, _ = c.verify_claims(
        ["N150"], lessons, ["scripts/hooks/x.py"], {"pre-commit"}, ["x"]
    )
    assert pos == 0 and no_ev == 0 and unk == 1


def test_write_record_first_creates_table(tmp_path, monkeypatch):
    rec = tmp_path / "claimed-activation.md"
    monkeypatch.setattr(c, "OPS_RECORD", rec)
    monkeypatch.setattr(
        "check_claimed_rules.datetime", type("DT", (), {
            "now": lambda tz: type("N", (), {"strftime": lambda s, f: "2026-08-15 12:00 UTC"})()
        })
    )
    c._write_record("abc12345", ["N151"], ["N151"], [], 1.0)
    text = rec.read_text(encoding="utf-8")
    assert "| timestamp | commit | claimed | positive | no-evidence | rate | verdict |" in text
    assert "abc12345" in text
    assert "OK" in text


def test_write_record_idempotent(tmp_path, monkeypatch):
    rec = tmp_path / "claimed-activation.md"
    monkeypatch.setattr(c, "OPS_RECORD", rec)
    c._write_record("abc12345", ["N151"], ["N151"], [], 1.0)
    before = rec.read_text(encoding="utf-8")
    c._write_record("abc12345", ["N151"], ["N151"], [], 1.0)
    after = rec.read_text(encoding="utf-8")
    assert before == after


def test_write_record_append_second(tmp_path, monkeypatch):
    rec = tmp_path / "claimed-activation.md"
    monkeypatch.setattr(c, "OPS_RECORD", rec)
    c._write_record("abc12345", ["N151"], ["N151"], [], 1.0)
    c._write_record("def67890", ["N150"], [], ["N150"], 0.0)
    text = rec.read_text(encoding="utf-8")
    assert "abc12345" in text and "def67890" in text
    assert "LOW" in text


def test_write_record_na_semantics(tmp_path, monkeypatch):
    rec = tmp_path / "claimed-activation.md"
    monkeypatch.setattr(c, "OPS_RECORD", rec)
    monkeypatch.setattr(
        "check_claimed_rules.datetime", type("DT", (), {
            "now": lambda tz: type("N", (), {"strftime": lambda s, f: "2026-08-15 12:00 UTC"})()
        })
    )
    c._write_record("na11111", ["N200"], [], [], None)
    text = rec.read_text(encoding="utf-8")
    assert "| N/A | N/A |" in text
    assert "no-evidence" in text


def _row(commit: str, rate: float | None) -> dict:
    return {"commit": commit, "claimed": "N151", "positive": "N151",
            "no_evidence": "-", "rate": rate}


def test_review_trigger_insufficient_data():
    recs = [_row("a", 0.2), _row("b", 0.3)]
    trig, last3 = c.check_review_trigger(recs)
    assert trig is False and last3 == []


def test_review_trigger_low_rate_last3():
    recs = [_row("a", 0.2), _row("b", 0.9), _row("c", 0.1), _row("d", 0.4)]
    trig, last3 = c.check_review_trigger(recs)
    assert trig is True
    assert [r["commit"] for r in last3] == ["b", "c", "d"]


def test_review_trigger_na_skipped():
    recs = [_row("a", 0.2), _row("b", 0.1), _row("c", None),
            _row("d", 0.9), _row("e", None)]
    trig, last3 = c.check_review_trigger(recs)
    # 有效记录 = a(20%) b(10%) d(90%), 最近 3 条有效中 2 条 < 50% → 触发
    assert trig is True
    assert [r["commit"] for r in last3] == ["a", "b", "d"]


def test_review_trigger_all_na_skipped():
    recs = [_row("a", None), _row("b", None), _row("c", None)]
    trig, _ = c.check_review_trigger(recs)
    assert trig is False  # 全部 N/A → 数据不足


def test_write_review_trigger_idempotent(tmp_path, monkeypatch):
    rec = tmp_path / "claimed-activation.md"
    monkeypatch.setattr(c, "OPS_RECORD", rec)
    rec.write_text("| timestamp | commit | claimed | positive | no-evidence | rate | verdict |\n"
                   "|---|---|---|---|---|---|---|\n"
                   "| t | `aaa11111` | N151 | - | - | 20% | LOW |\n"
                   "| t | `bbb22222` | N151 | - | - | 10% | LOW |\n"
                   "| t | `ccc33333` | N151 | - | - | 90% | OK |\n", encoding="utf-8")
    last3 = [_row("aaa11111", 0.2), _row("bbb22222", 0.1), _row("ccc33333", 0.9)]
    assert c._write_review_trigger("ddd44444", last3) is True
    assert c._write_review_trigger("ddd44444", last3) is False  # 幂等
    assert c.REVIEW_MARKER in rec.read_text(encoding="utf-8")


def test_load_records_6col_compat(tmp_path, monkeypatch):
    rec = tmp_path / "claimed-activation.md"
    monkeypatch.setattr(c, "OPS_RECORD", rec)
    rec.write_text("| timestamp | commit | claimed | positive | rate | verdict |\n"
                   "|---|---|---|---|---|---|\n"
                   "| t | `aaa11111` | N151 | - | 0% | LOW |\n"
                   "| t | `bbb22222` | N151 | N151 | 100% | OK |\n", encoding="utf-8")
    rows = c.load_records()
    assert len(rows) == 2
    assert rows[0]["rate"] == 0.0 and rows[1]["rate"] == 1.0
    assert rows[0]["no_evidence"] == "-"


def test_load_records_7col_na(tmp_path, monkeypatch):
    rec = tmp_path / "claimed-activation.md"
    monkeypatch.setattr(c, "OPS_RECORD", rec)
    rec.write_text("| timestamp | commit | claimed | positive | no-evidence | rate | verdict |\n"
                   "|---|---|---|---|---|---|---|\n"
                   "| t | `aaa11111` | N200 | - | - | N/A | N/A |\n"
                   "| t | `bbb22222` | N151 | - | N151 | 0% | LOW |\n", encoding="utf-8")
    rows = c.load_records()
    assert len(rows) == 2
    assert rows[0]["rate"] is None  # N/A 语义
    assert rows[1]["no_evidence"] == "N151" and rows[1]["rate"] == 0.0


def test_main_no_claims(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "_git", lambda *a, **kw: "abc12345\nfeat(x): plain\n")
    monkeypatch.setattr(c, "OPS_RECORD", tmp_path / "claimed-activation.md")
    assert c.main([]) == 0


def test_main_with_claims_records(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "_git", lambda *a, **kw: "abc12345\nfeat(x): N151\n")
    monkeypatch.setattr(
        c, "collect_diff", lambda *a, **kw: (["docs/x.md"], set(), ["# architecture-first"])
    )
    monkeypatch.setattr(c, "load_lessons", lambda *a, **kw: [
        _lesson("N151-arch.md", ["architecture-first"])
    ])
    monkeypatch.setattr(c, "OPS_RECORD", tmp_path / "claimed-activation.md")
    assert c.main([]) == 0
    assert "abc12345" in (tmp_path / "claimed-activation.md").read_text(encoding="utf-8")


def test_rule_files_filters_rule_dirs():
    paths = [
        ".skills/rules/env-hardrules.md",
        ".ai-memory/meta/failure-modes.md",
        "scripts/hooks/check_claimed_rules.py",
        "scripts/lessons/promote_lessons.py",
        ".pre-commit-config.yaml",
        "docs/specs/active/x.md",
        "backend/apps/core/models.py",
        "frontend/src/app.ts",
    ]
    assert c._rule_files(paths) == [
        ".skills/rules/env-hardrules.md",
        ".ai-memory/meta/failure-modes.md",
        "scripts/hooks/check_claimed_rules.py",
        "scripts/lessons/promote_lessons.py",
        ".pre-commit-config.yaml",
        "docs/specs/active/x.md",
    ]


def test_rule_files_includes_specs():
    assert c._rule_files(["docs/specs/active/x.md"]) == ["docs/specs/active/x.md"]


def test_rule_files_excludes_ops_record():
    paths = [".ai-memory/ops/claimed-activation.md", ".ai-memory/ops/why-skipped.md"]
    assert c._rule_files(paths) == []  # OPS_RECORD 自身不触发 NO-CLAIM 自记录


def test_main_no_claims_rule_files_records(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "_git", lambda *a, **kw: "abc12345\nfeat(x): plain\n")
    monkeypatch.setattr(
        c, "collect_diff",
        lambda *a, **kw: ([".ai-memory/meta/failure-modes.md"], set(), []),
    )
    monkeypatch.setattr(c, "OPS_RECORD", tmp_path / "claimed-activation.md")
    assert c.main([]) == 0
    text = (tmp_path / "claimed-activation.md").read_text(encoding="utf-8")
    assert "abc12345" in text
    assert "NO-CLAIM" in text
    assert ".ai-memory/meta/failure-modes.md" in text


def test_main_no_claims_no_rule_files_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "_git", lambda *a, **kw: "abc12345\nfeat(x): plain\n")
    monkeypatch.setattr(
        c, "collect_diff", lambda *a, **kw: (["backend/apps/core/models.py"], set(), [])
    )
    monkeypatch.setattr(c, "OPS_RECORD", tmp_path / "claimed-activation.md")
    assert c.main([]) == 0
    assert not (tmp_path / "claimed-activation.md").exists()  # 非规则文件不记录


def test_behavioral_claim_exempt_from_low():
    # N192 在 BEHAVIORAL_N 中: 即使无 diff 证据, 也不计入 no_evidence / 分母
    claimed = ["N192"]
    lessons = []          # 无 lesson, 但行为类豁免优先于 unknowable 判定
    changed_paths, tokens, added_lines = [], set(), []
    pos, no_ev, unk, behav, positive, no_evidence = c.verify_claims(
        claimed, lessons, changed_paths, tokens, added_lines
    )
    assert behav == 1, f"N192 应计入 behavioral, got {behav}"
    assert no_ev == 0, f"行为类不应计入 no_evidence, got {no_ev}"
    assert unk == 0


def test_only_behavioral_claims_yield_na_rate():
    # 全部为行为类声称 -> effective 分母=0 -> rate=None (N/A), 不触发复盘
    claimed = ["N192", "N204"]
    lessons, changed_paths, tokens, added_lines = [], [], set(), []
    pos, no_ev, unk, behav, _, _ = c.verify_claims(
        claimed, lessons, changed_paths, tokens, added_lines
    )
    total = len(claimed)
    effective = total - unk - behav
    assert effective == 0
    assert (pos / effective if effective else None) is None


def test_code_claim_without_evidence_still_low():
    # N191 (schema) 有 lesson + diff_keywords 但 diff 不含 -> 仍 no_evidence
    fake_lesson = {"path": "N191-schema.md", "diff_keywords": ["params_config"]}
    claimed = ["N191"]
    changed_paths, tokens, added_lines = ["src/foo.py"], set(), ["x=1"]  # 不含 params_config
    pos, no_ev, unk, behav, _, no_evidence = c.verify_claims(
        claimed, [fake_lesson], changed_paths, tokens, added_lines
    )
    assert no_ev == 1 and behav == 0, "代码类无证据必须计 no_evidence"
    assert no_evidence == ["N191"]


def test_td382_behavioral_rules_exempt_from_low():
    # TD-382: 扩展后的行为类规则(如 N182 三维根因 / N109 决策自决 / N199 环境归一)
    # 声称无 diff 证据也计入 behavioral, 不进 no_evidence/分母 → 不再误判 0% LOW
    for n in ("N182", "N109", "N199", "N205", "N188", "N190"):
        claimed = [n]
        lessons = []          # 无 lesson 也豁免 (行为类优先于 unknowable)
        changed_paths, tokens, added_lines = [], set(), []
        pos, no_ev, unk, behav, _, _ = c.verify_claims(
            claimed, lessons, changed_paths, tokens, added_lines
        )
        assert behav == 1, f"{n} 应计入 behavioral, got behav={behav}"
        assert no_ev == 0, f"{n} 不应计入 no_evidence, got {no_ev}"


def test_no_claim_record_idempotent(tmp_path, monkeypatch):
    rec = tmp_path / "claimed-activation.md"
    monkeypatch.setattr(c, "OPS_RECORD", rec)
    monkeypatch.setattr(
        "check_claimed_rules.datetime", type("DT", (), {
            "now": lambda tz: type("N", (), {"strftime": lambda s, f: "2026-08-17 12:00 UTC"})()
        })
    )
    assert c._write_no_claim_record("abc12345", [".ai-memory/meta/failure-modes.md"]) is True
    before = rec.read_text(encoding="utf-8")
    assert c._write_no_claim_record("abc12345", [".ai-memory/meta/failure-modes.md"]) is False
    assert rec.read_text(encoding="utf-8") == before


_TD383_HEADER = (
    "| timestamp | commit | claimed | positive | no-evidence | rate | verdict |\n"
    "|---|---|---|---|---|---|---|\n"
)


def _td383_rec(tmp_path, rows: list[str], with_marker: bool = True):
    rec = tmp_path / "claimed-activation.md"
    text = _TD383_HEADER + "".join(rows)
    if with_marker:
        text += f"{c.REVIEW_MARKER} (snapshot aaa11111,bbb22222, trigger ccc33333)\n"
    rec.write_text(text, encoding="utf-8")
    return rec


def test_unclosed_review_stale_marker_auto_closes(tmp_path):
    # TD-383: 标记未写回复盘, 但当前有效记录已不满足触发条件 -> 自然闭环不阻塞
    rows = [
        "| t | `aaa11111` | N151 | N151 | - | 90% | OK |\n",
    ]
    assert c.check_unclosed_review(_td383_rec(tmp_path, rows)) == 0


def test_unclosed_review_fresh_trigger_still_blocks(tmp_path, capsys):
    # TD-383: 标记未写回复盘且最近 3 条有效中 >=2 条 LOW -> 仍阻塞 (真实触发不豁免)
    rows = [
        "| t | `aaa11111` | N151 | - | N151 | 20% | LOW |\n",
        "| t | `bbb22222` | N151 | - | N151 | 10% | LOW |\n",
        "| t | `ccc33333` | N151 | N151 | - | 90% | OK |\n",
        "| t | `ddd44444` | N151 | - | N151 | 30% | LOW |\n",
    ]
    rec = _td383_rec(tmp_path, rows)
    assert c.check_unclosed_review(rec) == 1
    assert "REVIEW_TRIGGERED" in capsys.readouterr().out


def test_unclosed_review_closed_marker_passes(tmp_path):
    # 已有 📋 复盘写回 -> 直接通过 (原有行为不变)
    rec = _td383_rec(tmp_path, [
        "| t | `aaa11111` | N151 | - | N151 | 20% | LOW |\n",
        "| t | `bbb22222` | N151 | - | N151 | 10% | LOW |\n",
    ])
    text = rec.read_text(encoding="utf-8")
    rec.write_text(text.rstrip("\n") + f"\n{c.REVIEW_CLOSURE_MARK} 已复盘\n", encoding="utf-8")
    assert c.check_unclosed_review(rec) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
