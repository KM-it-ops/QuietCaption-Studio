# Model Move Byte Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify every copied model byte and active-role pointer against strict local manifests before a model-directory move can publish the destination or delete the source.

**Architecture:** Reuse one explicit-root local manifest validator for runtime readiness, installed-model Verify, and staged-move verification. The move transaction computes the installed descriptor set from the immutable source root, verifies the staged destination with descriptor identity/path/hash checks plus active-pointer consistency, and promotes only after every check passes. Existing lifecycle exclusion, live leases, UUID-owned staging, cleanup warnings, and root revalidation remain unchanged.

**Tech Stack:** Python pathlib/json/SHA-256, existing `ModelService` transaction and journal primitives, pytest fault-injection fixtures.

## Global Constraints

- Follow `AGENTS.md`: every pytest command uses a unique `.pytest-runs\<timestamp>` base, `--basetemp`, and `-p no:cacheprovider`.
- No real model/catalog network access; all fetchers and model trees are local fixtures.
- The complete source tree and `registry.root` remain unchanged until staged destination byte verification succeeds and promotion commits.
- Any verification/promotion failure preserves source bytes, active pointers, and authoritative root; cleanup removes only the current UUID-owned staging path.
- Continue to distinguish local post-install consistency from trusted catalog provenance; this task does not claim catalog trust.
- Preserve cross-instance leases, OS mutation locks, rollback journals, warning semantics, concurrent-move acquisition retry, demo behavior, and adapter compatibility.
- Do not implement catalog hashes/signatures, Custom Setup, settings propagation, queue concurrency, languages, or media work.

---

### Task 1: Strict explicit-root manifest and staged-registry verification

**Files:**
- Modify: `src/quietcaption/model_service.py`
- Test: `tests/test_model_service.py`
- Create: `.superpowers/sdd/model-move-byte-verification-task-1-report.md`

**Interfaces:**
- Consumes: `ModelService._verify_at_root(descriptor, registry_root) -> bool`, normalized-root mutation state, live-use guards, UUID move staging, and cleanup warnings.
- Produces: strict `ModelService._verify_local_manifest(root: Path, descriptor: ModelDescriptor) -> bool` (or the same behavior under the existing explicit-root name) that validates manifest identity, safe listed paths, and bytes under exactly `root`.
- Produces: `_verify_registry_copy(staged_root: Path, installed: tuple[ModelDescriptor, ...]) -> bool`, independent of mutable `registry.root`, validating every installed descriptor and active-role pointer in the staged tree.

- [ ] **Step 1: Write failing byte-corruption and source-preservation tests**

Add a local two-model fixture. Monkeypatch `shutil.copytree` to call the real copy and then alter one staged `model.bin` while leaving `.complete` and `manifest.json` intact. Call default `move()` and assert it raises an integrity error, `registry.root` remains the source, the full source snapshot is byte-identical, destination is unpublished/unchanged, and only the UUID staging path is removed.

- [ ] **Step 2: Run the corruption RED test**

Run `tests/test_model_service.py -k "move_rejects_corrupted_staged_bytes"` with the required unique base/cache-disabled options.

Expected: FAIL because `_verify_registry_copy()` currently checks only marker/manifest existence.

- [ ] **Step 3: Write failing manifest identity/path/completeness tests**

Parameterize staged-copy mutations for:

- manifest `id`, `kind`, `revision`, or `repo_id` mismatch;
- missing listed file or wrong listed SHA-256;
- absolute, parent-traversing, or symlink-escaping listed path;
- unexpected unlisted regular model payload (allow only `manifest.json` and `.complete` outside the manifest's `files` map);
- empty/non-dict `files` map;
- active pointer with malformed JSON, unknown descriptor, wrong role, or descriptor not installed in the staged tree.

Every case must reject before source deletion and preserve source/root byte-for-byte.

- [ ] **Step 4: Run manifest/pointer RED tests**

Run `tests/test_model_service.py -k "move_rejects_invalid_staged_manifest or move_rejects_invalid_staged_active_pointer"` with a fresh required base.

Expected: at least identity/unlisted/pointer cases FAIL under current existence-only staged verification.

- [ ] **Step 5: Implement one strict explicit-root validator**

Refactor the existing explicit-root verification so it:

- resolves the model root strictly beneath the explicit registry root;
- requires manifest object fields `id`, `kind`, `revision`, and `repo_id` to equal the descriptor;
- requires `files` to be a non-empty `dict[str, str]` with 64-character hexadecimal SHA-256 values;
- rejects absolute/traversing/symlink-escaping paths and requires each target to be a regular file contained below the resolved model root;
- hashes every listed file;
- rejects unlisted regular payload files except `manifest.json` and `.complete`;
- validates `.complete` equals the descriptor revision.

Make runtime acquisition and `verify()` reuse this same function so staged moves do not create a weaker second algorithm.

- [ ] **Step 6: Implement staged registry and pointer verification**

Capture `source_root` and the tuple of descriptors installed at that root before copying. Pass that immutable tuple into the default staged verifier. For each staged `active-<kind>.json`, require an object with one string `id`, find a catalog descriptor with matching role, and require its strict local manifest to pass under the staged root. Do not call `registry.is_installed()`, `active()`, or another helper that rereads mutable `registry.root` during staged verification.

- [ ] **Step 7: Run focused GREEN verification**

Run all new move/manifest/pointer tests, then `tests/test_model_service.py` with fresh unique bases.

Expected: all pass; the existing Windows symlink fixture may remain the sole environment-specific skip when `WinError 1314` prevents fixture creation.

- [ ] **Step 8: Run full/static verification and record evidence**

Run the full suite once with a fresh required basetemp, redirected compileall with a unique workspace-local `PYTHONPYCACHEPREFIX`, and `git diff --check`. Write exact RED/GREEN commands/output and self-review to `.superpowers/sdd/model-move-byte-verification-task-1-report.md`.

- [ ] **Step 9: Commit after independent approval**

After the task reviewer reports no Critical or Important findings, commit the focused source/test slice and factual ledger update with conventional subjects. Do not bundle catalog-trust terminology or Custom Setup.
