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
