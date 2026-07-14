# Settings Schema Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject malformed settings types consistently and make fallback from a malformed on-disk file visibly distinguishable from a clean default configuration.

**Architecture:** Centralize explicit field-type/domain validation in `SettingsStore.validate`, normalizing all persistence-boundary failures to `SettingsValidationError` naming the field. Add a non-mutating `load_result()` result carrying settings plus an optional recovery warning; retain `load()` as a compatibility wrapper. Settings UI surfaces the warning without rewriting or deleting the malformed source.

**Tech Stack:** Python frozen dataclasses, JSON, atomic writes, PySide6, pytest.

## Global Constraints

- Preserve valid schema migration and portable export/import behavior.
- Never replace or modify a settings file when validation/import fails.
- Do not combine runtime import/reset propagation into this slice; that has its own audit boundary.
- Every pytest run follows the unique `.pytest-runs\<timestamp>` basetemp rule.

---

### Task 1: Typed persistence boundary and visible malformed-file recovery

**Files:**
- Modify: `src/quietcaption/settings.py`
- Modify: `src/quietcaption/ui/settings_view.py`
- Modify: `src/quietcaption/ui/main_window.py`
- Test: `tests/test_settings_schema.py`
- Test: `tests/test_product_ui.py`
- Create: `.superpowers/sdd/task-settings-schema-hardening-report.md`

**Interfaces:**
- Produces: frozen `SettingsLoadResult(settings: AppSettings, warning: str | None)`.
- Produces: `SettingsStore.load_result() -> SettingsLoadResult`; `load()` returns `.settings` for compatibility.
- Preserves: `save`, `import_from`, and `reset_section` atomicity.

- [ ] **Step 1: Write schema RED tests** parameterized over wrong-type values: `queue_concurrency="2"`, `queue_concurrency=True`, `theme=7`, `update_checks="yes"`, `gpu_fallback=1`, non-string paths, and invalid schema version. Assert `SettingsValidationError` names the exact field and failed save/import leaves destination bytes unchanged.

- [ ] **Step 2: Write recovery RED tests** for malformed JSON and one malformed field. Assert `load_result()` returns defaults plus a warning containing path and field/error, while the original bytes remain identical; missing file returns defaults with no warning.

- [ ] **Step 3: Run RED** with `tests/test_settings_schema.py -k "type or malformed or recovery"` under a fresh required basetemp. Expected: FAIL because validation is partial and `load_result` does not exist.

- [ ] **Step 4: Implement explicit validation**. Check booleans with `type(value) is bool`; integers with `type(value) is int` before ranges; strings before choices/path/language/model fields; and schema version as an integer migrated to the current version. Wrap constructor/comparison/type failures as `SettingsValidationError` with the field name. Do not coerce strings or booleans.

- [ ] **Step 5: Implement non-destructive load results**. Catch missing-file separately; for parse/migration/validation errors return defaults plus an actionable warning without rewriting the source. Make Settings UI show that warning at construction/reload and keep technical details local/path-specific.

- [ ] **Step 6: Run focused GREEN** on `tests/test_settings_schema.py tests/test_product_ui.py` with a fresh base. Expected: all targeted tests PASS and existing migrations remain green.

- [ ] **Step 7: Run full verification and record evidence**. Use a fresh full-suite basetemp, redirected compileall, and `git diff --check`; write the exact RED/GREEN output to the task report.

- [ ] **Step 8: Commit after independent approval** with `git commit -m "fix: harden settings schema validation"`, including only this slice's code/tests/report and the factual ledger update.

