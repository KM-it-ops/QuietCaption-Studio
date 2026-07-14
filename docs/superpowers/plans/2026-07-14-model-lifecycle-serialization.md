# Model Lifecycle Serialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure only one install, update, repair, activate, remove, move, or automated-bundle mutation can affect a model registry at a time, while respecting queue model-use leases.

**Architecture:** Put exclusion at the `ModelService` boundary, keyed by resolved registry root so multiple service instances coordinate. Use one explicit transaction wrapper and private unlocked primitives so composite repair/automated operations do not deadlock. Expose a single busy state to `ModelsView`, which disables every conflicting action for the operation lifetime.

**Tech Stack:** Python filesystem locking, existing `filesystem_lock.py` when compatible, PySide6 workers/signals, pytest barriers.

## Global Constraints

- Implement only after `2026-07-14-queue-runtime-snapshot-readiness.md` is approved.
- A live model-use lease always wins; `force=True` cannot bypass it.
- Tests use local fetchers and deterministic barriers only; no model or catalog network access.
- Failed/busy operations preserve installed bytes and active pointers and clean only owned staging artifacts.
- Every pytest run follows the unique workspace-local basetemp rule in `AGENTS.md`.

---

### Task 1: Serialize registry mutations and bind all Models controls to one busy state

**Files:**
- Modify: `src/quietcaption/model_service.py`
- Modify: `src/quietcaption/filesystem_lock.py` only if its owner/stale contract fits; otherwise create `src/quietcaption/model_operation_lock.py`
- Modify: `src/quietcaption/ui/models_view.py`
- Test: `tests/test_model_service.py`
- Test: `tests/test_product_ui.py`
- Create: `.superpowers/sdd/task-model-lifecycle-serialization-report.md`

**Interfaces:**
- Produces: `ModelOperationBusy(RuntimeError)` with an actionable registry-root message.
- Produces: `ModelService.mutation()` context manager and private `_install_unlocked`, `_activate_unlocked`, `_remove_unlocked`, `_move_unlocked` primitives.
- Produces: one `ModelsView._set_lifecycle_busy(bool)` path covering Automated Setup and all mutating buttons.

- [ ] **Step 1: Write service RED concurrency tests** using a blocking local fetcher and two `ModelService` instances for the same root. While install is held, update/repair/remove/activate/move must raise `ModelOperationBusy` before changing any path. Add a repair test proving the composite transaction does not self-deadlock and restores old bytes/pointer on failure.

- [ ] **Step 2: Run service RED** with `tests/test_model_service.py -k "busy or serial or transaction"` using a fresh required basetemp. Expected: FAIL because lifecycle calls enter independently.

- [ ] **Step 3: Implement registry-root exclusion** with one lock acquisition per public composite operation and private unlocked primitives. Normalize root identity with `Path.resolve()`. Acquire before deleting staging/backup or writing pointer files. Preserve queue lease checks inside the transaction.

- [ ] **Step 4: Run service GREEN** with the Step 2 command and a fresh base. Expected: PASS; the blocked contender leaves a byte-for-byte identical tree.

- [ ] **Step 5: Write UI RED tests** that hold an operation open and assert install/update/repair/activate/remove and Automated Setup are all disabled; success and failure restore the valid enabled state and actionable status.

- [ ] **Step 6: Implement one busy-state UI path**. Route every asynchronous lifecycle operation through one worker helper, reject synchronous activate/remove while busy, keep worker references alive until terminal signal, and restore controls in one completion/failure method.

- [ ] **Step 7: Run focused and full GREEN verification** with unique bases; record RED/GREEN output in the task report; run redirected compileall and `git diff --check`. Expected: all PASS/exit 0.

- [ ] **Step 8: Commit after independent approval** with `git commit -m "fix: serialize model lifecycle mutations"`, including only the files and report for this slice plus the factual ledger update.
