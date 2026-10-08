# PRAXIS — lcm-hygiene

## Problem

Hermes-LCM has been silently storing deterministic head/tail truncation as if it were a real LLM summary. 608 / 1161 summary nodes (52.4%) carry the `[...deterministic truncation...]` marker; 405 of those have non-empty `source_ids` (recoverable via `lcm_expand` → re-summarize), 203 have empty `source_ids` (permanently lossy text fragments). The 30s "Context compression timed out" warning has been firing intermittently, but that is the *honest* signal — the dishonest signal is the silently-saved L3 output being treated as a summary in recall, condensation, and downstream consumers.

The structural contradiction: a circuit breaker exists (failure_threshold=2, cooldown=300s) to protect against hot loops hitting a failing summary route, but the L3 fallback it eventually triggers produces an output that is well-shaped enough (correct token count, correct compression ratio, no error raised) to pass every shape check and get indexed into `nodes_fts` as if it were real.

## Goal

**Recover** the 405 recoverable corrupted nodes (replace L3 with real L1/L2 summaries via `lcm_expand` → re-summarize → UPDATE), **characterize** the 203 permanently lossy nodes (date buckets, depth distribution, sample text), **stop** the bleed (apply refined Edit 1+2+3 from R1R3 refinement: `LCM_SUMMARY_TIMEOUT_MS=90000`, `LCM_LEAF_CHUNK_TOKENS=2000`, fix config.yaml Frankenstein model name), **document** (durable project workspace that any future session can resume from cold).

## In scope

- Codex synthesis on magnitude for `LCM_SUMMARY_TIMEOUT_MS` (read-only, fed the GLM transcript).
- Apply refined Edit 1+2 (env, gateway restart).
- Apply Edit 3 (config.yaml Frankenstein fix, hot-reload).
- Run recovery script `--limit 5` validation on the 812 MB DB copy at `/tmp/lcm_recovery_test.db`.
- Snapshot pre/post L3 counts.
- Inventory the 203 unrecoverable nodes.
- (Optional, post-M1) Run `--live` re-summarization on the 405.
- Trace Mnemosyne read-path (does Mnemosyne read `summary_nodes` or raw `messages`?).
- File Mnemosyne durable facts + a `hermes-agent` or `hermes-lcm-aak-contribution` wiki page.

## Out of scope (explicit)

- Replacing hermes-lcm with a different memory engine (assessed separately; opencode-mem is NOT a substitution, see `projects/audits/opencode-mem-audit.md`).
- Speculative magnitude changes without Codex synthesis.
- Live LLM recovery unless `--live` flag is passed AND Codex's magnitude recommendation is applied first.
- Editing any file under `~/projects/hermes-lcm/` (read-only — that is the source tree; we deliver scripts and audit findings, not upstream patches).
- Restructuring `summary_nodes` schema or the L3 fallback itself (out of project scope; would require upstream hermes-lcm changes).
- Reformatting the 203 unrecoverable nodes (their source_ids are empty; the text is what it is).

## Evidence ownership

| Data type | Owning module | Persistence |
|-----------|---------------|-------------|
| L3 count + buckets | `~/.hermes/lcm.db` `summary_nodes` table | SQLite, raw on disk |
| Pre/post snapshots | This project's `evidence/snapshots/` | Markdown, dated |
| Recovery script | This project's `scripts/lcm_recover.py` | Python, version-controlled in this repo only |
| Codex synthesis transcript | This project's `evidence/codex-synthesis-<ts>.txt` | Plain text, dated |
| Audit trail | `~/hermes-vault/audits/` (parent, R1, R3) | Markdown, immutable historical record |
| Mnemosyne facts | Mnemosyne private bank | Vector + FTS, importance-tagged |

## Risk gates

- **Pre-M1 (gate before Edit 1+2):** Codex synthesis on magnitude is on disk at `evidence/codex-synthesis-<ts>.txt`. Without this, M1 cannot be claimed — Edit 1's number is ungrounded.
- **M1 → M2:** `scripts/verify.sh` M1 section exits 0; L3 count has plateaued (no growth during restart window).
- **M2 → M3:** `evidence/snapshots/lcm-lossy-inventory-<ts>.md` exists with date buckets, depth distribution, sample text for the 203.
- **M3 → M4:** `scripts/verify.sh` M3 section exits 0; L3-with-source_ids count drops from 405 to ≤ noise floor.
- **M4 → done:** Mnemosyne read-path verdict filed at `evidence/mnemosyne-readpath-<ts>.md`; scaffold files all present and dated; verify.sh runs end-to-end; next session can resume cold from `EXECUTION-PROMPT.md`.

## Definition of done

- M1-M4 all verified by their respective verify.sh gates.
- All numeric claims in `STATUS.md` backed by literal commands that were actually run.
- Mnemosyne durable fact filed summarizing the project and pointing to the next session's resume entry point.
- `hermes-vault/wiki/` (or wiki equivalent) page exists with cross-references.
- `EXECUTION-PROMPT.md` exists and is self-contained (next agent can run it cold).

## Open unknowns (research / spike)

- **Magnitude for LCM_SUMMARY_TIMEOUT_MS** — Codex synthesis pending (load-bearing; see EXECUTION-PROMPT).
- **Mnemosyne read-path** — does sleep-time consolidation read `summary_nodes` or `messages`? Proven impact is LCM recall + condensation only; Mnemosyne path is one trace away from being claimed clean or claimed poisoned.
- **Whether 90000ms is the right number** — R1R3 refinement says 90000 matches the audit's "120" precedent; the original GLM framing said 60000. Codex's read of the transcript will resolve.

## Re-plan triggers

- Codex's synthesis disagrees with the GLM transcript's literal evidence → re-delegate a second GLM run with a strictly scoped brief (no free-form open-ended "review").
- L3 count continues to grow after Edit 1+2 application → bleed not stopped; re-plan to investigate circuit breaker threshold (currently 2 failures, 300s cooldown — maybe lower the threshold so L3 path triggers sooner on broken routes).
- `--live` recovery fails on more than 10% of the 405 → re-plan to either widen the LLM call budget or accept the recoverable subset only.