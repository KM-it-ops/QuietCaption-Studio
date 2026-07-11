# Project Constraints & Learnings

- On this Windows Codex workspace, never reuse `.tmp-test` or rely on the user temp directory for local pytest runs after packaging or escalated commands. Create a unique workspace-local directory under `.pytest-runs\<timestamp>`, pass it explicitly with `pytest --basetemp <path>`, and disable the cache with `-p no:cacheprovider`; reused or fallback temp directories can inherit ACLs that produce `WinError 5: Access is denied`.
- Release UI must not contain placeholder navigation pages or hand-maintained short language lists. Every visible tab must provide its documented workflow, and language selectors must be generated from model capability metadata so the UI exposes only languages supported by the active local transcription or translation model.
