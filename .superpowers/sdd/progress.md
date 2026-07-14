# QuietCaption Studio completion ledger

Baseline: `cbfac14` on `agent/full-product-expansion`; 66 tests passed on 2026-07-13.

Collision-safe outputs: complete (commits `cbfac14..63cde68`, 81 tests passed, task review clean).
Auto-learning rule: committed as `fa14673`.

Durable editor and final data-safety hardening: complete (commits `fa14673..25f64d0`, 149 tests passed on exact HEAD, broad review clean).
User-data-protection phase: complete at `25f64d0`; ready for the visible-controls/runtime-configuration phase.

Transcription beam runtime wiring: complete (strict RED/GREEN recorded, focused tests passed (32), full suite passed (156), task review approved with no Critical or Important findings on 2026-07-14). The New Job beam value is now snapshotted per queue and reaches Faster-Whisper without changing demo behavior.
Final review: ready to merge. Minor follow-ups: strengthen backend tests with multiple non-default values plus the implicit default of 5; optionally reject non-integer `TranscriptionOptions.beam_size` values if this internal value becomes a public programmatic API.

Compute-device and GPU-fallback runtime wiring: complete on 2026-07-14.

- RED: `python -m pytest -q tests/test_runtime.py tests/test_settings_schema.py tests/test_translation.py tests/test_product_ui.py tests/test_control_contract.py --basetemp .pytest-runs/<unique> -p no:cacheprovider` stopped during collection with 1 expected error because `resolve_compute` did not exist.
- Initial GREEN attempt: the same focused command reached 55 passed and 1 failed; the sole failure was a test case-sensitivity mismatch against the brief's exact actionable `Enable GPU fallback or select CPU` wording. The assertion was corrected without changing production behavior.
- GREEN: the same focused command with a fresh unique base passed 56 tests in 5.18s.
- Regression: `python -m pytest -q --basetemp .pytest-runs/<unique> -p no:cacheprovider` with a fresh unique base passed 173 tests in 10.29s.
- Static verification: `python -m compileall -q src` passed with a unique workspace-local `PYTHONPYCACHEPREFIX`; `git diff --check` passed.
- Initial task review: needs fixes. Review found that unavailable-CUDA preflight also blocked demo queues and that adding `compute_type` before legacy positional `engine`/`tokenizer` parameters broke existing constructor bindings. Portable GPU-fallback transfer/reset assertions were also requested. Corrections are in progress; re-review is pending.
- Existing scope note: runtime backend failures after a successfully detected CUDA profile remain surfaced normally and are intentionally outside this preflight policy task.

Compute-device review corrections: implemented on 2026-07-14; re-review pending.

- Regression RED: the 5-test covering command for demo preflight, legacy three-/four-positional NLLB construction, explicit compute type, and portable fallback transfer/reset produced 3 expected failures and 2 passes. Demo created no worker, and both legacy positional forms bound to the wrong constructor fields.
- Regression GREEN: the same 5-test command with a fresh unique base passed 5 tests in 0.89s.
- Focused verification: the compute/settings/translation/product-UI/control-contract set passed 60 tests in 5.35s with a fresh unique base.
- Full regression verification: the full suite passed 177 tests in 11.25s with a fresh unique base.
- Corrections: unavailable-CUDA preflight now applies only to production queues; demo still constructs its normal worker. `engine` and `tokenizer` retain their legacy positional slots, while `compute_type` is keyword-only and production passes it explicitly by keyword. Portable export/import and Processing reset now have direct fallback assertions.
- Re-review: approved at `96ec098` with no Critical, Important, or Minor findings. The reviewer confirmed demo behavior, legacy NLLB positional compatibility, explicit fallback transfer/reset coverage, and the new project-local learning rules.

Broad full-product branch review after the compute slice: not merge-ready; no Critical findings. The compute/fallback slice itself remained approved. Important follow-up boundaries are: implement the real Custom Setup workflow; snapshot output/model inputs per queue and coordinate model-in-use state; serialize model lifecycle mutations; implement queue concurrency separately; apply imported/reset settings immediately; harden malformed settings types; hash-verify model moves before source deletion; add authoritative native language names and suppress semantic self-translation; and gate Generate on active-model readiness. Minor findings: restore reachable FFmpeg burn-in and distinguish local manifest consistency from trusted catalog hashes. These are subsequent reviewed tasks and were not folded into the compute/fallback task.

Queue runtime snapshot, readiness, and model-use ownership: complete on 2026-07-14 (commits `6ec4bab..122bf04`).

- Queue-start output, compute, transcription options, exact transcription/translation runtimes, and leases are now immutable for every file; demo queues retain their no-model and production-only-CUDA-preflight behavior.
- Generate readiness now combines selected files, local production model readiness, and queue-idle state with accessible Models guidance.
- Service-owned leases block destructive install/update/repair/remove/move operations for in-use models, including forced removal, and release idempotently on completion, failure, cancellation, adapter construction failure, and pool-start failure.
- Initial task review found one Important exact-directory gap for absolute/traversing/symlinked manifest entries. Commit `122bf04` added resolved-root containment and focused RED/GREEN coverage; re-review approved with no Critical, Important, or Minor findings.
- Fresh exact-head verification at `122bf04`: full suite `194 passed, 1 skipped in 128.39s`; the skip is the Windows symlink regression fixture denied by `WinError 1314`, while absolute and parent-traversal regressions pass. Redirected compileall and `git diff --check 6ec4bab..HEAD` exited 0.

Model lifecycle serialization and failure atomicity: complete on 2026-07-14 (commits `122bf04..04d5d5c`).

- Normalized-root lifecycle mutations now use persistent non-blocking OS byte locks, shared cross-instance lease state, UUID-owned artifacts, one transaction for composite repair/Automated Setup, and a unified Models UI busy-state that also protects Verify.
- Mutation journals restore installed bytes and active pointers on pre-commit failure. Move/remove/journal post-commit cleanup failures preserve one authoritative valid state and expose read-only cleanup warnings/residual paths without deleting ambiguous artifacts.
- The first task review found cross-instance lease bypass, racy stale-lock recovery, incomplete composite rollback, unowned fixed staging, and Verify overlap. Commit `dc0fc9a` corrected these with focused RED/GREEN coverage.
- Re-review then found move/remove/journal cleanup failure-atomicity gaps; commit `ad28497` added logical commit points, reversible forced removal, non-fatal owned cleanup warnings, weak root-state retention, and removed obsolete stale-lock configuration.
- The final allowed re-review found a Critical move-vs-runtime-acquisition stale-root race. Commit `04d5d5c` added explicit-root capture/lock/revalidation/retry and same-root pointer/install/manifest/hash validation plus destination-root lease enforcement.
- Final independent re-review at `04d5d5c`: approved with no Critical, Important, or Minor findings. Implementer verification: focused `73 passed, 1 skipped`; full suite `222 passed, 1 skipped`; redirected compileall and `git diff --check` passed.

Typed settings schema validation and malformed-file recovery: complete on 2026-07-14 (commit `0aa48ab`).

- Every `AppSettings` field now has an explicit type/domain contract; booleans are not accepted as integers, values are not coerced, and persistence-boundary errors name the exact field.
- `SettingsLoadResult` distinguishes a missing clean-default file from malformed JSON/schema fallback. Malformed sources remain byte-identical and Settings UI exposes the actionable recovery warning on construction/reload.
- Legacy migration, compatibility `load()`, portable import/export filtering, reset behavior, and atomic writes remain intact.
- Independent task review: approved with no Critical or Important findings. Minor follow-up: import read/decoding/JSON failures currently share “could not be parsed” wording; differentiating unreadable files from malformed JSON would improve diagnostics.
- Implementer verification: RED `35 failed`; new-behavior GREEN `51 passed`; focused `92 passed`; full suite `273 passed, 1 skipped`; redirected compileall and `git diff --check` passed.
