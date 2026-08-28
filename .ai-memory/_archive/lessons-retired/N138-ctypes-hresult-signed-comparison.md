---
date: 2026-06-30
symptom: [agent-platform, com, ctypes, HRESULT, signed-comparison, win32]
solution: ctypes.c_long (HRESULT) is signed — error codes like E_FAIL (0x80004005) appear as negative numbers. Compare with (hr & 0xFFFFFFFF) == E_FAIL, never hr == E_FAIL.
related_files:
  - agent/src/platforms/windows/_com_delegate.py
  - agent/src/platforms/windows/wgc.py
  - agent/tests/test_com_delegate.py
  - agent/tests/test_wgc.py
created_by: AI
priority: medium
cross_refs: []
level: L1
n_id: N138
topic: agent-platform
---

# N138 — Python ctypes HRESULT Signed Comparison Gotcha

## Symptom (症状)

Two tests in `agent/tests/test_com_delegate.py` failed after writing COM delegate
vtable tests:

- `test_invoke_returns_e_fail_on_exception`
- `test_query_interface_returns_e_nointerface_for_unknown_iid`

The assertions compared the returned `HRESULT` directly against error constants:
```python
assert hr == E_FAIL              # E_FAIL = 0x80004005
assert hr == E_NOINTERFACE       # E_NOINTERFACE = 0x80004002
```
These assertions failed because `hr` was `-2147467259`, not `0x80004005`, even
though the COM call had correctly returned `E_FAIL`.

## Root Cause (根因)

`HRESULT` is defined as `ctypes.c_long`, which is a **signed** 32-bit integer.
COM error codes have the high bit set (e.g. `E_FAIL = 0x80004005`), so when
stored in a signed `c_long` they appear as **negative** numbers:

| Constant | Hex | Signed c_long |
|----------|-----|---------------|
| S_OK | 0x00000000 | 0 |
| E_FAIL | 0x80004005 | -2147467259 |
| E_NOINTERFACE | 0x80004002 | -2147467262 |
| E_INVALIDARG | 0x80070057 | -2147024809 |

Direct equality (`hr == E_FAIL`) compares a negative int against a positive hex
literal and always returns `False`, masking real bugs — a test that should catch
a broken COM path instead passes the bug through.

## Fix (修复)

Compare using an unsigned mask:
```python
# WRONG — hr is signed, E_FAIL is a positive hex literal
assert hr == E_FAIL

# RIGHT — mask to unsigned 32-bit before comparing
assert (hr & 0xFFFFFFFF) == E_FAIL
```

Or define a helper:
```python
def hr_succeeded(hr: int) -> bool:
    return hr >= 0  # S_OK == 0; success codes are non-negative

def hr_failed(hr: int, expected: int) -> bool:
    return (hr & 0xFFFFFFFF) == expected
```

## Prevention (预防)

- Any `ctypes.c_long` / `c_int32` field holding a value with the high bit set
  (HRESULT, NTSTATUS, Win32 error codes) is **signed** — always mask with
  `& 0xFFFFFFFF` before comparing against hex constants.
- When writing COM/Win32 tests in the agent, prefer the `(hr & 0xFFFFFFFF) == X`
  pattern or a `hr_succeeded` / `hr_failed` helper. Never use bare `==`.
- The same applies to `c_ulong` comparisons in the opposite direction (rare).
- This recurs in any `platforms/windows/` COM work (WGC, ADB via Win32, future
  UIAutomation, etc.).

## Evidence (3 步)

- **Problem**: `test_invoke_returns_e_fail_on_exception` and
  `test_query_interface_returns_e_nointerface_for_unknown_iid` failed;
  `hr` was `-2147467259` instead of `0x80004005`.
- **Solution**: Changed assertions to `(hr & 0xFFFFFFFF) == E_FAIL` /
  `(hr & 0xFFFFFFFF) == E_NOINTERFACE`. Commit `-`.
- **Verification**: 25/25 tests in `test_com_delegate.py` pass; 42/42 tests in
  `test_wgc.py` pass (total 67 agent COM tests green).

## Related

- `agent/src/platforms/windows/_com_delegate.py` — defines `HRESULT = ctypes.c_long`.
- `agent/src/platforms/windows/wgc.py` — WGC COM calls return HRESULT.
- P2-1 WinRT FrameArrived callback work (commit `-`).
