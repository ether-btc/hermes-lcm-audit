# ROADMAP — lcm-hygiene

## Sequencing principle

**Riskiest first, but revised.** The original sequencing assumed "M1 fixes silent truncation." The classified inventory (`evidence/snapshots/lcm-lossy-inventory-2026-08-25_22-50.md`) shows that M1 fixes the timeout-shaped subset (≤31% of L3 markers) but the 68% capacity-shaped subset requires a separate input-token guard at the LCM level (`hermes-lcm/escalation.py:545`). Per GLM-5.2 reviewer verdict (2026-08-25 22:49), **Phase 3 (recovery) is BLOCKED** until the guard lands — premature recovery permanently consumes the idempotency predicate on capacity-shaped nodes.

Revised sequencing: M1 ✅ → Phase 2 inventory ✅ → Phase 2.5 input-token guard ✅ → Phase 3 recovery ✅ (dry-run validated; live write owner-gated) → Phase 4 docs ✅.

## Phase 3 dry-run close-out (DONE 2026-08-26 ~03:48)

- **Population truth:** 147 raw ≤3500-stc marker rows − 116 `[stub-recovery]` placeholders = **31 real recoverable nodes**. Global: 452 recoverable / 446 permanently lossy (>8000 stc).
- **Full zero-write dry-run:** exit 0, 14 LLM would-writes + 17 cross-session skips, failed=[], 0×402, ~78.7 s/node. Zero-write proven empirically (byte-identical node contents post-run; live count unchanged).
- **New finding (v2.1 candidate):** chars/4 estimator undercounts dense text → occasional safe degradation to deterministic fallback after server-side context rejection.
- **Routing rule:** standalone recovery MUST use `--local-only`; standalone aux client resolves `auto`→dead OpenRouter and swallows 402s internally.
- **Tool hardening landed:** `--max-source-tokens`, `--stratify`, EmptySummary guard in `scripts/lcm_recover.py`.
- **Gate to real recovery (OWNER):** snapshot + `lcm_recover.py --db ~/.hermes/lcm.db --live --local-only --confirm-live --backup <path> --max-source-tokens 3500`. Mid-bucket (57) and large-bucket (446) decisions remain owner calls; large bucket needs a bigger-context model or chunk-and-stitch.

## M1 — Stop the bleed (DONE 2026-08-25 22:42)

- [x] T0 — Codex synthesis on magnitude. Done: 90000ms, both knobs. Cited `gateway/run.py:19538-19572` (hygiene as idle fence).
- [x] T1 — Pre-edit snapshot. Latest: `evidence/snapshots/pre-edit-20260825_204134.txt`.
- [x] T2 — Apply env `LCM_SUMMARY_TIMEOUT_MS=90000` (was 60000, was 45000 in earlier audit).
- [x] T3 — Apply env `LCM_LEAF_CHUNK_TOKENS=2000` (applied earlier; still in place).
- [x] T4 — Restart gateway. Active since 2026-08-25 22:41:56.
- [x] T5 — Post-restart snapshot. Latest: `evidence/snapshots/post-edit-20260825_204217.txt`.
- [x] T6 — Apply YAML `compression.hygiene_timeout_seconds: 120` (the phantom-key claim was wrong — ADR-2026-08-25-05; this is a real hot-reloadable knob).
- [x] T-V — Independent verification: verify.sh post-restart = 9/9 PASS.

**M1 gate:** ✅ L3 count plateaued (delta=0 at restart, +3 capacity-shaped since); gateway alive; both knobs visible.

**M1 caveat:** M1 addresses the parent-batch/latency failure mode (gateway/run.py:19538-19572). It does NOT address the single-call/large-input failure mode that produced 68% of historical L3 markers. A separate fix (Phase 2.5) is required.

## Phase 1 — Stop the bleed (DONE)

### T1 — Snapshot pre-edit state  ✅
### T2 — Apply Edit 1 (LCM_SUMMARY_TIMEOUT_MS)  ✅
### T3 — Apply Edit 2 (LCM_LEAF_CHUNK_TOKENS)  ✅ (was applied earlier)
### T4 — Restart gateway  ✅
### T5 — Snapshot post-restart state  ✅
### T6 — Apply Edit 3 (config.yaml Frankenstein fix)  ✅ (was applied earlier; the new YAML knob is `hygiene_timeout_seconds: 120`)

**M1 gate:** ✅ T1-T6 all done; L3 count plateaued for ≥ 1 hour after restart (started 2026-08-25 22:42).

### T-V — Independent verification (live re-run)
- Re-run the 5-step verification from `lcm-silent-truncation-verification-2026-08-25.md` against the live DB.
- **Done:** numbers match the snapshot; no silent drift.

## Phase 2 — Characterize the loss (DONE 2026-08-25 22:50)

### T7 — Inventory the 203 unrecoverable + 448 recoverable nodes with cause-axis classification
- Query for date buckets, depth distribution, session concentration, source_token_count distribution.
- File at `evidence/snapshots/lcm-lossy-inventory-<ts>.md`.
- **Done:** `lcm-lossy-inventory-2026-08-25_22-50.md` — full inventory with cause-axis classification.

**Classification results (2026-08-25 22:50):**
| bucket | count | %    | M1 impact |
|--------|------:|-----:|-----------|
| capacity-fit (≤3500 stc)   | 144 | 22%  | partial (timeout raise) |
| mid-overflow (3501-8000)   |  61 |  9%  | none (input too large) |
| **large-overflow (>8000)** | **446** | **68%** | **none** |
| TOTAL | 651 | 100% | M1 covers ≤31% |

Largest: node 1609, source_token_count=211,781 (51× n_ctx=4096).

**M2 gate:** ✅ T7 done. **New finding:** M1's scope is 22-31% of historical L3; the 68% capacity-shaped majority requires Phase 2.5.

## Phase 2.5 — LCM input-token guard (BLOCKED, AWAITING OWNER APPROVAL)

This phase is **new** since the ROADMAP was last revised. The reviewer verdict makes it explicit: Phase 3 cannot run safely without this guard.

### T7.1 — Patch `hermes-lcm/escalation.py:545` with pre-flight token-budget guard
- Add ~10-line guard at the top of `summarize_with_escalation`: if `count_tokens(text) > (model_ctx − output_reserve)`, head/tail-truncate using existing `_truncate_text_to_tokens` (`escalation.py:465`) and head/tail assembler (`escalation.py:519-524`).
- Annotate truncated summaries so audits distinguish "summary of truncated input" from clean summaries.
- Why LCM-level (not gateway): gateway's idle fence is a *timeout* mechanism, not a sizing mechanism; the recovery script (`lcm_recover.py:113, :228`) calls `summarize_with_escalation` directly — a gateway guard would leave Phase 3 unprotected.
- **Done:** guard committed to hermes-lcm; `scripts/verify.sh --phase inventory` shows axis=fit=* higher (more capacity-fit, fewer overflow) after a session.

**M2.5 gate:** ✅ T7.1 done; observation window over 1 long session shows fit-axis markers only, no overflow-axis.

## Phase 3 — Recover (BLOCKED until Phase 2.5 lands)

### T8 — Add safety gates to `scripts/lcm_recover.py` (BLOCKED, AWAITING OWNER APPROVAL)
- Add `--confirm-live` flag.
- Refuse `--live` or `--stub` against `~/.hermes/lcm.db` unless a same-session backup exists at `$BACKUP_PATH`.
- LLM call happens outside the transaction — flag this and document the read-against-mutating-state risk.
- Reviewer finding: `--stub` is a one-way door (stubbed rows excluded from future candidate selection by NOT LIKE predicate at `lcm_recover.py:26`).

### T9 — Validate recovery script --live path
- Run `scripts/lcm_recover.py --db /tmp/lcm_recovery_test.db --limit 5 --dry-run` first.
- Then run `scripts/lcm_recover.py --db /tmp/lcm_recovery_test.db --limit 5` (FTS-only validation per Codex v2 brief).
- Verify FTS postings match `summary_nodes.summary` for the 5 updated rows.
- Verify final integrity-check passes.
- **Done:** `evidence/snapshots/lcm-recover-validate-<ts>.txt` shows updated=5, skipped_idempotent=0, integrity-check ok.

### T10 — Run --live recovery on capacity-fit subset
- Run `scripts/lcm_recover.py --live --db /tmp/lcm_recovery_test.db --limit 144` (capacity-fit subset only).
- **Done:** L3-with-source_ids count drops; verify.sh M3 section exits 0.

### T11 — Run --live recovery on mid-overflow subset
- Same as T10 but `--limit 61`. Phase 2.5 guard required.

### T12 — Run --live recovery on large-overflow subset
- **PROBABLY NOT VIABLE.** Requires a larger-context model. Skip until (a) Qwen3-8B or similar available on host, or (b) chunk-and-stitch pipeline implemented. Owner decision required.

### T13 — Snapshot post-recovery state
- Run `scripts/verify.sh --phase post-recovery`.
- **Done:** L3-with-source_ids near zero (excluding the 446 unrecoverable-large); total summary count unchanged (rows replaced, not inserted).

**M3 gate:** T8-T13 all done. Large-overflow subset (446) may remain permanently lossy — owner accepts.

## Phase 3.5 — Policy migration (BLOCKED, AWAITING OWNER APPROVAL)

### T-M1 — Migrate env `LCM_SUMMARY_TIMEOUT_MS=90000` → `auxiliary.compression.timeout: 90` in YAML
- Per AGENTS.md: "behavioral settings — timeouts, thresholds, feature flags — go in config.yaml."
- hermes-lcm/config.py:266-278 reads `auxiliary.compression.timeout` (seconds, ×1000) FIRST; env wins on precedence at config.py:837-841.
- **ATOMIC EDIT required:** add YAML AND remove env in same commit + one gateway restart.
- verify.sh already accepts either state (env OR YAML) — no verify.sh change needed for the check, but the check description was updated 2026-08-25 22:52.

## Phase 4 — Durable

### T14 — Trace Mnemosyne read-path
- One grep + one read; verdict: Mnemosyne reads `summary_nodes` OR `messages` (with line citations).
- File at `evidence/mnemosyne-readpath-<ts>.md`.
- **Done:** dated verdict file.

### T15 — Mnemosyne durable fact + wiki page
- File a Mnemosyne fact summarizing the project (importance 0.7).
- File a wiki page in `ether-btc/wiki` (if that path is reachable) or an equivalent surface.
- **Done:** Mnemosyne memory ID + wiki page path captured in STATUS.md.

**M4 gate:** T14-T15 done; verify.sh exits 0 end-to-end; EXECUTION-PROMPT.md exists.

## Cross-phase gates

- Every status edit must update the "Last updated" stamp + re-run verify.sh (per project-planning evidence rule).
- Every numeric claim in STATUS.md must be backed by a literal command and a log path.
- Every config edit must be reversible (snapshot pre + diff post).
- Per ADR-2026-08-25-04: verify.sh re-derives every numeric claim.

## Re-plan triggers

- Codex synthesis disagrees with the GLM transcript's literal evidence. *(Not triggered.)*
- L3 count continues to grow on timeout-axis after Phase 1 edits. *(Not triggered: growth is on capacity-axis only.)*
- L3 count continues to grow on capacity-axis after Phase 2.5. *(Would invalidate the input-token guard.)*
- `--live` recovery fails on >10% of any subset.
- A new failure mode surfaces during recovery that wasn't in the original 3-model review.

## Confidence

- ~~Pre-Phase-1: LOW until Codex synthesis lands.~~ **Pre-Phase-1: RESOLVED.** Codex synthesis landed 22:40; magnitude 90000ms, both knobs, cited idle fence.
- ~~Phase 1: HIGH (Edits 1-3 are scoped, reversible, env-restart only).~~ **Phase 1: DONE.** 9/9 PASS post-restart. Caveat: covers 22-31% of historical L3 markers, not the 68% capacity-shaped majority.
- **Observation window:** MEDIUM. 2-3 long sessions needed. So far only capacity-axis growth (expected; Phase 2.5 fix). Zero timeout-axis growth (M1 working).
- **Phase 2:** HIGH (read-only inventory, no execution risk). **DONE** at 22:50 with cause-axis classification.
- **Phase 2.5:** MEDIUM. Touches upstream hermes-lcm code. Owner approval required. Required for Phase 3 to be safe.
- **Phase 3:** Dry-run COMPLETE 2026-08-26. Live FIT recovery COMPLETE (`c36a57a`). R0 17:38 CEST: **true_marker=0**, FIT residue empty. Remaining MID/LARGE **accepted** (ADR-2026-08-26-12).
- **Phase 4:** HIGH. **DONE 2026-08-26** (dry-run docs) and **refiled 17:45 CEST** (R0/R1 closeout).