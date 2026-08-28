# M2 行为类声称豁免 + commit-message 纪律 实现计划

> **面向 AI 代理的工作者：** 本计划用 TDD 小步任务实现。步骤用复选框（`- [ ]`）跟踪进度。
> **执行建议：** 本计划涉及改 `scripts/hooks/check_claimed_rules.py` 及其测试，需在**新对话**中执行（本对话已过长，避免长上下文幻觉；用户 2026-08-22 已提示此风险）。

**目标：** 消除「AI 在 commit message 中声称行为/合规类 N##（如 N192 双调试、N204 诊断）但 diff 无代码证据」时被 M2 误判为 LOW、反复触发 `REVIEW_TRIGGERED` 的摩擦。

**架构：** 两层修复——
1. **主修复（纪律，无代码）**：AI 不在 commit message 写 N## 编号，除非该 commit 的 diff 确实改了对应规则文件且含其 `diff_keywords` 证据。这是 `check_claimed_rules.py` 的设计意图（防"声称多、证据薄"），hook 本身无 bug。
2. **可选增强（本计划代码部分）**：在 `check_claimed_rules.py` 增加「行为/合规类 N##」豁免集，使这类声称即使无 diff 证据也不计入 LOW 分母（视作 N/A，与 `unknowable` 同类处理），降低误触发。

**技术栈：** Python 3.11（conda gaf）；pytest；pre-commit hook。

---

## 背景校正（重要，避免追 phantom）

- 本会话早前反复提及的 **TD-382 并非已注册技术债**——它只出现在本会话自己的复盘与 spec-context 中，仓库内无任何注册定义。本计划不引用 TD-382。
- 早前的诊断「M2 对含 N## 提及的 diff 敏感」**错误**：hook 从 **commit message** 提取声称的 N## 并核验 **diff 证据**，与 diff 是否含 N## 字样无关。本轮 M2 阻塞主因是 AI 在 message 里写 N## 当"声称"但 diff 无证据（如 message 写"修复 N191 指向…"而 diff 仅是链接文本）。
- 真实根因 = commit-message N## 卫生纪律缺失。代码增强只是可选的人体工学改进。

---

## 文件结构

- 修改：`scripts/hooks/check_claimed_rules.py` — 增加 `BEHAVIORAL_N` 豁免集，`verify_claims()` 将行为类声称归入豁免（不计入 `no_evidence`、不进分母）。
- 修改：`scripts/tests/test_check_claimed_rules.py` — 新增行为类豁免的单测 + 回归（代码类声称仍判 LOW）。
- 修改（纪律载体）：`.ai-memory/meta/ai-operating-handbook.md` 或新增 lesson — 记录"commit message 勿随意声称 N##"的纪律。
- 参考（只读）：`scripts/lessons/match_lessons_by_diff.py`（`collect_diff` / `load_lessons` 来源）。

---

### 任务 1：新增行为类豁免集与单测（TDD 红）

**文件：**
- 修改：`scripts/hooks/check_claimed_rules.py`
- 测试：`scripts/tests/test_check_claimed_rules.py`

- [ ] **步骤 1：先读现有测试文件，掌握 fixture 写法**

运行：`Get-Content scripts/tests/test_check_claimed_rules.py`（或 Read）
预期：了解如何构造 `lessons` / `changed_paths` / `tokens` / `added_lines` 入参（无真实 git 依赖的纯函数测试路径）。

- [ ] **步骤 2：编写失败测试——行为类声称应豁免**

在 `test_check_claimed_rules.py` 末尾追加：

```python
def test_behavioral_claim_exempt_from_low():
    # N192 在 BEHAVIORAL_N 中: 即使无 diff 证据, 也不计入 no_evidence / 分母
    claimed = ["N192"]
    lessons = []          # 无 lesson, 但行为类豁免优先于 unknowable 判定
    changed_paths, tokens, added_lines = [], set(), []
    pos, no_ev, unk, behav, positive, no_evidence = verify_claims(
        claimed, lessons, changed_paths, tokens, added_lines
    )
    assert behav == 1, f"N192 应计入 behavioral, got {behav}"
    assert no_ev == 0, f"行为类不应计入 no_evidence, got {no_ev}"
    assert unk == 0


def test_only_behavioral_claims_yield_na_rate():
    # 全部为行为类声称 -> effective 分母=0 -> rate=None (N/A), 不触发复盘
    claimed = ["N192", "N204"]
    lessons, changed_paths, tokens, added_lines = [], [], set(), []
    pos, no_ev, unk, behav, _, _ = verify_claims(
        claimed, lessons, changed_paths, tokens, added_lines
    )
    total = len(claimed)
    effective = total - unk - behav
    assert effective == 0
    assert (pos / effective if effective else None) is None
```

- [ ] **步骤 3：运行测试确认失败**

运行：`D:\code\environment\conda\envs\gaf\python.exe -m pytest scripts/tests/test_check_claimed_rules.py::test_behavioral_claim_exempt_from_low -v`
预期：FAIL（`verify_claims` 当前返回 5 元组，无 `behav`；且 N192 无 lesson → 进 `unk`，非 `behav`）。

- [ ] **步骤 4：Commit（红）**

```bash
git add scripts/tests/test_check_claimed_rules.py
git commit -m "test: 新增行为类 N## 声称豁免的单测 (红)"
```

---

### 任务 2：在 `verify_claims` 实现行为类豁免（TDD 绿）

**文件：**
- 修改：`scripts/hooks/check_claimed_rules.py`

- [ ] **步骤 1：新增豁免集常量（文件顶部，靠近 RULE_DIRS）**

```python
# 行为/合规类规则: AI 遵守但 diff 无代码证据 (如双调试视角 N192 / 诊断触发 N204
# / 任务归属 N193). 这类声称不应拖低激活率, 视作 N/A 豁免 (与 unknowable 同类,
# 不计入 no_evidence, 不进分母). 列表与 failure-modes.md Active 段行为类条目对齐.
BEHAVIORAL_N = {"N192", "N204", "N193"}
```

- [ ] **步骤 2：修改 `verify_claims` 返回行为类计数**

将函数签名与循环改为（保留原 positive/no_evidence/unknowable 逻辑，仅插入行为类早退）：

```python
def verify_claims(
    claimed, lessons, changed_paths, tokens, added_lines,
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
                if (any(kw in p for p in changed_paths)
                        or kw in tokens
                        or any(kw in line for line in added_lines)):
                    hit = True
                    break
            if hit:
                break
        (positive if hit else no_evidence).append(n)
    return (len(positive), len(no_evidence), len(unknowable),
            len(behavioral), positive, no_evidence)
```

- [ ] **步骤 3：更新 `main` 的调用与分母计算**

在 `main` 中（约 372 行附近）：

```python
    positive_n, no_ev_n, unk_n, behav_n, positive, no_evidence = verify_claims(
        claimed, lessons, changed_paths, tokens, added_lines,
    )
    total = len(claimed)
    effective = total - unk_n - behav_n   # 分母排除 unknowable + 行为类豁免
    rate = positive_n / effective if effective else None
```

并同步更新 `_write_record` 调用处的解包（若有）以容纳新返回值（当前仅 `main` 解包，已改）。

- [ ] **步骤 4：运行任务 1 测试确认通过**

运行：`D:\code\environment\conda\envs\gaf\python.exe -m pytest scripts/tests/test_check_claimed_rules.py -v`
预期：PASS（含 `test_behavioral_claim_exempt_from_low` / `test_only_behavioral_claims_yield_na_rate`）。

- [ ] **步骤 5：Commit（绿）**

```bash
git add scripts/hooks/check_claimed_rules.py scripts/tests/test_check_claimed_rules.py
git commit -m "feat(hooks): M2 行为类 N## 声称豁免, 不计入 LOW 分母 (N192/N204/N193)"
```

---

### 任务 3：回归——代码类声称仍判 LOW（防过度豁免）

**文件：**
- 测试：`scripts/tests/test_check_claimed_rules.py`

- [ ] **步骤 1：编写测试——代码类声称无证据仍 LOW**

```python
def test_code_claim_without_evidence_still_low():
    # N191 (schema) 假设存在 lesson 且 diff_keywords 不在本次 diff -> no_evidence
    # 用一个确定有 lesson + diff_keywords 的 N## 模拟; 若无 fixture, 直接构造 lessons 入参:
    fake_lesson = {"path": "N191-schema.md", "diff_keywords": ["params_config"]}
    claimed = ["N191"]
    changed_paths, tokens, added_lines = ["src/foo.py"], set(), ["x=1"]  # 不含 params_config
    pos, no_ev, unk, behav, _, no_evidence = verify_claims(
        claimed, [fake_lesson], changed_paths, tokens, added_lines
    )
    assert no_ev == 1 and behav == 0, "代码类无证据必须计 no_evidence"
    assert no_evidence == ["N191"]
```

- [ ] **步骤 2：运行确认通过**

运行：`D:\code\environment\conda\envs\gaf\python.exe -m pytest scripts/tests/test_check_claimed_rules.py -v`
预期：PASS。

- [ ] **步骤 3：Commit**

```bash
git add scripts/tests/test_check_claimed_rules.py
git commit -m "test: 回归代码类 N## 无证据仍判 LOW, 防过度豁免"
```

---

### 任务 4：纪律载体（主修复的真正落点）

**文件：**
- 修改：`.ai-memory/meta/ai-operating-handbook.md`（L2 行为红线段）或新增 `.ai-memory/lessons/N2xx-commit-message-no-claim.md`

- [ ] **步骤 1：沉淀纪律**

在 handbook 行为红线或新建 lesson 中记录：
> **commit message 勿随意声称 N##**：M2 (`check_claimed_rules.py`) 从 message 提取声称的 N## 并以 diff 证据核验；声称了但 diff 无对应 `diff_keywords` 证据 → 激活率拉低 → 可能触发 `REVIEW_TRIGGERED`。仅在 commit 真实改动该规则文件且含证据时才在 message 写 N##；否则用文字描述（如"修复情境约束链接"）而非编号。

- [ ] **步骤 2：Commit**

```bash
git add .ai-memory/meta/ai-operating-handbook.md
git commit -m "docs(handbook): 沉淀 commit message 勿随意声称 N## 的纪律"
```

---

### 任务 5：全量校验与提交

- [ ] **步骤 1：跑 hook 测试全集**

运行：`D:\code\environment\conda\envs\gaf\python.exe -m pytest scripts/tests/ -q`
预期：PASS（无回归）。

- [ ] **步骤 2：跑治理 hook（dry 预检，可选）**

运行：`D:\code\environment\conda\envs\gaf\python.exe scripts/hooks/check_claimed_rules.py --no-record`
预期：输出 M2 统计，无异常。

- [ ] **步骤 3：最终 Commit（若任务 4/5 有未提交）**

```bash
git status --short
git add -A && git commit -m "chore: M2 行为类豁免 + commit-message 纪律沉淀"
```

---

## 自检

1. **规格覆盖度**：目标（消除行为类声称误判 LOW）← 任务 2/3；主修复纪律 ← 任务 4；测试 ← 任务 1/3。覆盖完整。
2. **占位符扫描**：无 TODO/待定/补充细节。
3. **类型一致性**：`verify_claims` 返回 6 元组（pos,no_ev,unk,behav,pos_ns,no_ev_ns），任务 2/3 测试解包一致；`main` 解包已同步更新。✅
4. **风险**：`BEHAVIORAL_N` 为硬编码集合，需与 failure-modes 行为类条目人工对齐（注释已注明）；未来新增行为类规则须同步加此处。

---

## 实施完成 (2026-08-22, 同对话内合并推进 Spec A/B/C)

**实现方式偏离原始计划（经用户批准采用更优方案）：**

原始计划用 `BEHAVIORAL_N` 硬编码豁免集（仅覆盖 N192/N204/N193）。实际采用**更通用的「diff 痕迹豁免」**：`verify_claims()` 在 lesson 有 `diff_keywords` 但关键词未命中时，追加判据——若声称的 N## 字面出现在 diff 新增行或变更路径中，即视为内容关联证据（positive），不再误判为 naked 声称。该方案同时消解原 spec 目标（行为类声称不再拖低激活率），且覆盖更广（任何"规则文件里写了对应编号"的 commit 都算证据），无需人工对齐豁免集。

**落点 commit：** `-`（refactor(rules): v9.2 元规则出清机制 + L0 注入砍半 (spec A/B/C)）

**同 commit 附带的相关改动（本 spec 范围外但同源张力）：**
- Spec A：Active N## 硬上限 35 机械出清 + 棘轮 check-cap 守卫
- Spec B：L0 注入 38.5KB→17.1KB 瘦身
- Spec C-1/C-3：提交纪律口径唯一定案；判级后验 warn-only 钩子

**验证：** scripts/tests 588 passed, 2 skipped；governance batch 17/17 passed；pre-commit 全 16 hook 通过（含 B2 evidence + spec-context 载体）。

**状态：** ✅ 完成（原 5 任务中的代码目标由 diff-trace 豁免达成；任务 4 纪律载体已由 commit message 纪律节 + 本关闭段共同沉淀）。从 active 迁出由后续归档流程处理。
