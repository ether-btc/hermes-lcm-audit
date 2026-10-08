# DECISIONS — lcm-hygiene

Append-only ADR log. Status: `proposed | accepted | superseded by #N | invalidated`.

---

## 2026-08-25-01 — Edit 1 replacement (parent audit's `compression.hygiene_timeout_seconds` is a phantom key) — accepted

**Context.** The parent 3-model audit (`compression-30s-warning-3-model-review-2026-08-25.md`) recommended Option C, which included Edit 1: adding `compression.hygiene_timeout_seconds: 120` to `~/.hermes/config.yaml`. The R1R3 refinement (`lcm-silent-truncation-r1r3-refinement-2026-08-25.md`) audited every citation and found that key does **not exist** anywhere in hermes-agent or hermes-lcm. `grep -rn hygiene_timeout_seconds` returns zero. The actual hygiene trigger is `_hyg_threshold_pct = 0.85` hardcoded at `gateway/run.py:7947` plus `_HARD_MSG_LIMIT = 400` from `compression.hygiene_hard_message_limit` at line 7984. The proposed YAML patch would have been silently no-op'd by Hermes' config loader.

**Decision.** Replace Edit 1 with `LCM_SUMMARY_TIMEOUT_MS=90000` in `~/.config/hermes-gateway.env`. Edit is cold-knob (gateway restart required), not hot. Rationale: matches the audit's "120" intuition pointed at the right env knob instead of a phantom YAML key.

**Alternatives rejected.**
- (a) Add a NEW YAML key just to make Edit 1 work — out of scope; hermes-agent is upstream, we don't patch it here.
- (b) Lower LCM_SUMMARY_TIMEOUT_MS to 30000 to match the audit's stated "30s vs 45s structural inconsistency" framing — wrong direction; this would *shorten* the call budget when the issue is calls failing to complete.

**Evidence.** `evidence/lcm-silent-truncation-r1r3-refinement-2026-08-25.md` lines 21-22 (R1 citation audit); `evidence/deleg_7fbffac1-task-0.log` line 24 (GLM confirming only INSERT/DELETE triggers exist).

**Revisit condition.** If Hermes adds a real YAML key under `compression.*` that controls the hygiene trigger, re-evaluate.

---

## 2026-08-25-02 — Use Codex (gpt-5.6-sol) for magnitude synthesis, NOT a re-delegated GLM run — accepted

**Context.** The GLM R3 subagent (`deleg_7fbffac1`) ran 934s and its final synthesis was truncated mid-sentence at iteration 21. The transcript (`evidence/deleg_7fbffac1-task-0.log` line 76) shows the truncated start: `nodes_fts is confirmed as an external-content FTS5 table (content="summary_nodes", content_rowid="node_id`. The actual test work (TEST-A through TEST-E, 0.33s rebuild timing on 774MB, FTS verification of special-delete + INSERT) is fully captured. The magnitude call is missing.

**Decision.** Run Codex `codex exec` (gpt-5.6-sol on ChatGPT Plus OAuth, no override per 2026-08-24 operating model) in read-only sandbox to read the GLM transcript + parent audit + R1R3 refinement, and produce a single defensible magnitude with line citations. Do **not** re-delegate GLM — the same long-running pattern that caused the truncation would recur.

**Alternatives rejected.**
- (a) Re-delegate GLM with stricter iteration cap — `iterations=10` did not save the previous run because the work was deep exploration, not iteration overhead; capping iterations would just stop GLM mid-evidence-collection, not mid-synthesis.
- (b) Hermes synthesizes magnitude directly — violates audit discipline rule (independent review before implementing config changes; per Mnemosyne 2026-08-23).
- (c) Pick 60000ms (initial GLM framing) or 90000ms (R1R3 recommendation) without synthesis — ungrounded, exactly the gap we are closing.

**Evidence.** Mnemosyne 2026-08-24-00:13 (Codex stays on ChatGPT Plus OAuth, no override); Mnemosyne 2026-08-24-02:03 (independent reviews must use `codex exec`, not delegate_task); `evidence/deleg_7fbffac1/manifest.json` (`exit_reason: max_iterations`).

**Revisit condition.** If Codex's synthesis disagrees with the transcript's literal evidence, escalate to (a) with a strictly-scoped GLM brief (3 sentences max, no free-form review).

---

## 2026-08-25-03 — Recovery script FTS-only-first, --live opt-in — accepted

**Context.** Codex v2 build-task produced `scripts/lcm_recover.py` with the proven `delete-insert` pattern on external-content FTS5 (Codex v1 test showed `UPDATE` on `nodes_fts` raises `database disk image is malformed`). Codex scoped `--live` LLM recovery as opt-in so the FTS path ships first.

**Decision.** Adopt Codex's brief as-shipped. Validate `--limit 5` first (FTS-only), then opt into `--live` for the full 405 only after M1 lands.

**Alternatives rejected.**
- (a) Ship `--live` default — would re-trigger the circuit breaker on every row, which is exactly what produced the L3 corruption in the first place.
- (b) Custom recovery script — Codex's brief already won the v1/v2 test battle; rewriting would lose that knowledge.

**Evidence.** `evidence/codex-script-v2-stdout.txt` lines 19-21 (delete-insert proven); `evidence/codex-script-v2-stdout.txt` line 121 (--live opt-in requirement).

**Revisit condition.** If `--live` fails on >10% of the 405, re-plan to (a) raise the LCM_SUMMARY_TIMEOUT_MS even higher, (b) shrink leaf chunks further, or (c) accept FTS-only validation as the final state.

---

## 2026-08-25-05 — `compression.hygiene_timeout_seconds` IS a real key (R1R3 phantom-key claim retracted) — accepted

**Context.** The R1R3 refinement (`lcm-silent-truncation-r1r3-refinement-2026-08-25.md`) claimed `grep -rn hygiene_timeout_seconds` returns zero across hermes-agent + hermes-lcm, and concluded the parent audit's Edit 1 (`compression.hygiene_timeout_seconds: 120`) would be silently no-op'd. Re-verification 2026-08-25 22:32:

```bash
grep -n hygiene_timeout_seconds ~/projects/hermes-agent/gateway/run.py
# 19215:            _hyg_threshold_pct = 0.85
# 19258:                        _raw_hard_limit = _comp_cfg.get("hygiene_hard_message_limit")
# 19266:                        _raw_timeout = _comp_cfg.get("hygiene_timeout_seconds")
# ...
```

The key IS read at `gateway/run.py:19266`. Sibling keys `hygiene_total_ceiling_seconds` (line 19282) and `hygiene_failure_cooldown_seconds` (line 19299) are also real and live. The key is not currently SET in `~/.hermes/config.yaml` (default applies), but writing it would not be a no-op.

**Decision.** The R1R3 phantom-key claim is wrong. The parent's Edit 1 is a real, hot-reloadable fix. The R1R3 replacement (env `LCM_SUMMARY_TIMEOUT_MS=90000`) is also real, but cold-restart. **Both are valid levers** — the choice between them depends on whether the bleed is on the agent-compression side (YAML hygiene knob is the cleaner target) or the LCM-summary-call side (env knob is correct).

**Alternatives rejected.**
- (a) Restore the parent's Edit 1 literally as 120s without re-checking the codebase — that is exactly the audit error we are correcting.
- (b) Take the R1R3 env-knob recommendation at face value — same error in the opposite direction.

**Evidence.** `gateway/run.py:19240-19310` (live read), `~/.hermes/config.yaml` (key not set, defaults apply), `evidence/deleg_7fbffac1-task-0.log` (GLM ran the FTS work successfully; the magnitude call was what got truncated, not the lever choice).

**Revisit condition.** If `gateway/run.py` is refactored and the hygiene config block moves, re-verify.

---

## 2026-08-25-04 — Verify.sh re-derives every numeric claim — accepted

**Context.** Project-planning skill (validated 2026-08-23 on PROMPRO): a project's verified-facts table can drift across sessions ("91 tests passing" → "57 tests passing" with both verifier runs exiting 0). The fix is to anchor every claim to the literal command and the log file path.

**Decision.** `scripts/verify.sh` exits 0 only if (a) all 5-step live verification queries return values matching the most recent snapshot, (b) L3 count has not grown since snapshot, (c) env file has the expected keys, (d) config.yaml:111 has the corrected model name. Every STATUS.md numeric claim must include the literal command and log path.

**Alternatives rejected.**
- (a) Static file-existence checks only — misses the drift problem entirely.
- (b) Trust human-run SQL outputs — exactly the failure mode the rule prevents.

**Evidence.** Mnemosyne project-planning skill, validated 2026-08-23 PROMPRO drift case.

**Revisit condition.** None — this is a permanent evidence discipline.
---

## 2026-08-25-05 — Phantom-key retraction (R1R3 was wrong about hygiene_timeout_seconds) — accepted

**Context.** ADR-2026-08-25-01 claimed `compression.hygiene_timeout_seconds` is a phantom key. That claim was incorrect: the key IS read at `gateway/run.py:19266` (alongside `hygiene_total_ceiling_seconds` at 19282 and `hygiene_failure_cooldown_seconds` at 19299). All three are real hot-reloadable YAML knobs under `compression.*`. The R1R3 audit's `grep -rn hygiene_timeout_seconds` evidently missed these because the search path was scoped to lcm code, not gateway code.

**Decision.** Retract the phantom-key claim. Both knobs (`LCM_SUMMARY_TIMEOUT_MS` and `compression.hygiene_timeout_seconds`) are real and complement each other. Codex's T0 synthesis (`evidence/codex-synthesis-20260825_204001.txt`) correctly recommended moving both in lockstep to preserve the 30s outer margin.

**Alternatives rejected.**
- (a) Continue claiming phantom-key — leaves a valid lever unused and contradicts live code.
- (b) Revert the M1 YAML edit — would leave the outer fence at default (30s) and risk reverting the bleed fix.

**Evidence.** `grep -n 'hygiene_timeout_seconds' ~/projects/hermes-agent/gateway/run.py` returns 19266 (live, 2026-08-25 22:32).

**Revisit condition.** If the hygiene config block is refactored out of gateway/run.py, re-verify both keys.

---

## 2026-08-25-06 — M1 application record (Codex synthesis applied 2026-08-25 22:42) — accepted

**Context.** T0 (Codex magnitude synthesis) landed at 2026-08-25 22:40 (`evidence/codex-synthesis-20260825_204001.txt`) with verdict MAGNITUDE=90000, LEVER=both. Owner approved application at 22:42.

**Decision.** Apply both knobs in lockstep:
- `~/.config/hermes-gateway.env:29` → `LCM_SUMMARY_TIMEOUT_MS=90000` (was 60000; cold-restart knob)
- `~/.hermes/config.yaml` → `compression.hygiene_timeout_seconds: 120` (new key, hot-reloadable YAML knob)
- `systemctl --user restart hermes-gateway` (active since 2026-08-25 22:41:56)
- `scripts/verify.sh --phase post-restart` → 9/9 PASS at 22:42
- `scripts/verify.sh --phase post-edit` → L3 not grown (pre=648, now=648) at 22:42

**Alternatives rejected.**
- (a) Apply only the env knob (per R1R3) — left outer fence vulnerable (Codex's key insight at gateway/run.py:19538-19572).
- (b) Apply only the YAML knob (per parent audit's phantom Edit 1) — would not have addressed the cold-restart env wiring at hermes-lcm/config.py:834-842.

**Evidence.** `evidence/codex-synthesis-20260825_204001.txt`; `evidence/m1-application-2026-08-25_22-42.md`; `evidence/snapshots/{pre,post}-edit-20260825_*.txt`.

**Revisit condition.** If 2-3 representative long sessions produce new timeout-driven L3 markers, escalate per Codex's TRIGGER-TO-INCREASE (raise both knobs together, only if calls demonstrably hit 90000ms with model progress).

---

## 2026-08-25-07 — Observation-window monitoring script + new failure-mode discovery — accepted (revised by ADR-08)

**Context.** M1 verification completed at 22:42 with L3=648 and 9/9 PASS. To validate Codex's TRIGGER-TO-REVERT, we need to observe L3 count drift over the next 2-3 sessions. A drift-check script (`scripts/lcm_drift_check.sh`) was created for this purpose.

**First observation (22:45, 3 minutes after M1 gateway restart):** node 1760 appeared with `source_token_count=21099`, depth=0, summary_len=7648. This is a **different failure mode than M1 addresses**: a single-call summarization of ~21K tokens against Qwen2.5-0.5B (n_ctx=4096). The parent's "failure was capacity, not latency" diagnosis was correct; M1's timeout fix cannot solve a context-size problem.

**Decision.** Pause the observation window for the timeout fix and investigate the input-token-budget failure mode. Candidates:
- (a) Truncate source input to n_ctx budget before sending to summarizer (LCM_SUMMARY_MAX_INPUT_TOKENS knob).
- (b) Route large single-call summaries to a larger-context model (e.g., Qwen3-8B if available on the host).
- (c) Both.

**Alternatives rejected.**
- (a) Continue observation window in parallel — risk of accumulating more unrecoverable nodes while a fix is known to be needed.
- (b) Re-raise the timeout to 120000 (Codex's TRIGGER-TO-INCREASE) — explicitly disqualified by Codex: "context-overflow failures do not qualify."
- (c) Roll back M1 — M1 likely does fix the parent-batch-compression failure mode (the original 648 nodes); only the new single-call mode remains.

**Evidence.** `evidence/drift-log.txt` (first entry: L3=649, delta=+1, at 2026-08-25T20:45:42Z); `summary_nodes.node_id=1760` (source_token_count=21099, depth=0).

**Revisit condition.** If a second independent reviewer (Codex or GLM-5.3) confirms a different interpretation, supersede. **SUPERSEDED BY ADR-08 (classified inventory revealed 78% of L3 markers were always capacity-shaped).**

---

## 2026-08-25-08 — Sequencing reversal + Phase 2.5 (input-token guard) — accepted

**Context.** ADR-07 proposed a new failure-mode fix. GLM-5.2 reviewer verdict (`subagent sa-0-9d70a4f7`, 2026-08-25 22:49) expanded this finding into a sequencing reversal: the classified inventory at `evidence/snapshots/lcm-lossy-inventory-2026-08-25_22-50.md` shows **506 of 651 (78%) historical L3 markers were always capacity-shaped**, not timeout-shaped. The original "M1 fixes silent truncation" frame was wrong for the majority.

**Classified inventory (`evidence/snapshots/lcm-lossy-inventory-2026-08-25_22-50.md`):**
- 144 nodes capacity-fit (stc ≤ 3500) — M1 helps partially.
- 61 nodes mid-overflow (3501-8000) — M1 does not help.
- 446 nodes large-overflow (> 8000; up to 211K) — M1 does not help.

**Decision.** Reverse the sequencing. Phase 3 is now BLOCKED until a separate Phase 2.5 input-token guard lands at `hermes-lcm/escalation.py:545`.

Phase 2.5 spec:
1. Pre-flight guard at top of `summarize_with_escalation`: if `count_tokens(text) > (model_ctx − output_reserve)`, head/tail-truncate using existing `_truncate_text_to_tokens` (`escalation.py:465`) and head/tail assembler (`escalation.py:519-524`). ~10 lines.
2. Why LCM-level, not gateway: the recovery script `lcm_recover.py:113, :228` calls `summarize_with_escalation` directly; a gateway guard would leave Phase 3 unprotected.
3. Annotate truncated summaries so audits distinguish "summary of truncated input" from clean summaries.

Premature Phase 3 sharp edge (per lcm_recover.py:49-53): the idempotency predicate (only update rows still containing the truncation marker) would be permanently consumed on capacity-shaped nodes. After the guard, recovery would have a fresh chance at a high-fidelity summary; without it, recovery writes a low-fidelity summary of a 12K-char fragment and excludes those rows from future re-recovery.

**Alternatives rejected.**
- (a) Defer the input-guard and run Phase 3 anyway — permanently destroys recovery quality on 446 nodes. Reviewer sharp-edge finding.
- (b) Roll back M1 — M1 is still useful for the 144 capacity-fit nodes and for the gateway idle fence in general.
- (c) Skip the inventory and proceed with original plan — inventory revealed the 68% blind spot; without it we would have run Phase 3 blind.
- (d) Route to a larger model for capacity-shaped nodes — no such model exists on this host (only Qwen2.5-0.5B via llama-server).

**Evidence.** GLM-5.2 reviewer verdict (2026-08-25 22:49); `evidence/snapshots/lcm-lossy-inventory-2026-08-25_22-50.md`; `hermes-lcm/escalation.py:545` (entry point), `:465` (`_truncate_text_to_tokens`), `:519-524` (head/tail assembler).

**Revisit condition.** If the guard lands and a fresh Phase 3 dry-run shows the LLM call succeeds on capacity-shaped nodes (i.e., the guard fixed the failure), accept Phase 3 plan as-is. If a different architectural fix (e.g., chunk-and-stitch) proves more durable, supersede.

---

## 2026-08-25-09 — Policy migration: env LCM_SUMMARY_TIMEOUT_MS → auxiliary.compression.timeout in YAML — accepted (landed 2026-08-25; STATUS was stale)

**Context.** M1 set `LCM_SUMMARY_TIMEOUT_MS=90000` in `~/.config/hermes-gateway.env`. Per `projects/hermes-agent/AGENTS.md`: "New HERMES_* env vars for non-secret config. .env is for secrets only. All behavioral settings — timeouts, thresholds, feature flags, display prefs — go in config.yaml."

`hermes-lcm/config.py:266-278` reads `auxiliary.compression.timeout` (seconds, ×1000) from config.yaml FIRST; `_parse_int_env_with_source` (config.py:837-841) then overrides with env `LCM_SUMMARY_TIMEOUT_MS` if set. So env wins on precedence.

**Decision (proposed).** Migrate `LCM_SUMMARY_TIMEOUT_MS=90000` (env) → `auxiliary.compression.timeout: 90` (YAML).

**Atomic edit requirement:**
1. Add `auxiliary.compression.timeout: 90` to `~/.hermes/config.yaml` under the existing `auxiliary:` block at line 106 (next to `compression.model` at line 111).
2. Remove `LCM_SUMMARY_TIMEOUT_MS=90000` line from `~/.config/hermes-gateway.env`.
3. `systemctl --user restart hermes-gateway`.
4. `bash scripts/verify.sh --phase post-restart` must still pass (it accepts either env or YAML; updated 2026-08-25 22:52).

Doing only (1) without (2) leaves the env override in effect and changes nothing. Doing only (2) without (1) leaves the policy violation in place.

**Alternatives rejected.**
- (a) Keep env patch as-is — violates AGENTS.md.
- (b) Lower timeout to 7500ms to match something — wrong direction; the fix from M1 stays at 90000.

**Evidence.** `hermes-lcm/config.py:266-278` (YAML read), `:837-841` (env override); `projects/hermes-agent/AGENTS.md` (policy).

**Revisit condition.** None — once approved and applied, this is a permanent policy compliance fix.

---

## 2026-08-25-10 — lcm_recover.py safety gates — accepted (landed commit `463dab3`; STATUS was stale)

**Context.** Per GLM-5.2 reviewer verdict, `scripts/lcm_recover.py` has three sharp edges for live-DB use:
1. `--db ~/.hermes/lcm.db --live` immediately overwrites 448 live rows with no confirmation or backup precondition.
2. `--stub` is one-way: stubbed rows excluded from future candidate selection by `NOT LIKE` predicate at lcm_recover.py:26, permanently foreclosing real LLM recovery.
3. LLM call happens outside the transaction (lcm_recover.py:228-237 vs BEGIN IMMEDIATE at :35), so on live DB the summary can be computed from concurrently-mutating state.

**Decision (proposed).** Add safety gates before Phase 3:
1. `--confirm-live` flag. Without it, `--live` is rejected.
2. Refuse `--live` or `--stub` against `~/.hermes/lcm.db` unless a same-session backup exists at `$BACKUP_PATH` (env var) or `--backup <path>` is provided.
3. Document the read-against-mutating-state risk in the script docstring.

**Alternatives rejected.**
- (a) Run recovery on a separate DB copy, then atomic-rename — extra complexity for marginal benefit; the LLM call still happens against potentially-mutating state.
- (b) Disable --live entirely — Phase 3 needs it.

**Evidence.** GLM-5.2 reviewer verdict (2026-08-25 22:49); `scripts/lcm_recover.py:26` (NOT LIKE), `:35` (BEGIN IMMEDIATE), `:113`, `:228-237` (LLM call outside txn).

**Revisit condition.** None — once approved, the safety gates are permanent.


## 2026-08-25-11 — Phase 2.5: pre-flight input-budget guard + output-side cap for n_ctx=4096 — accepted (deployed 23:19 via symlink; fork `915bec0`)

**Context.** M1 (timeout-side fix) covers the 137 capacity-fit nodes (≤3000 source tokens). The remaining 514 nodes (61 mid + 446 large + 7 boundary-25) cannot fit `Qwen2.5-0.5B` n_ctx=4096 regardless of timeout. A previous Codev synthesis proposed a 3500-token input cap on `summarize_with_escalation` (commit 50bef1c in fork `hermes-lcm-phase25/`).

GLM-5.2 second-opinion review (subagent `sa-0-b0c31a6a`, 2026-08-25 23:07) found three issues with the v1 patch:

1. **Output-side overflow (critical).** `summarize_with_escalation` calls the LLM with `max_tokens = token_budget * 2`, which is ≥4000 for every node the guard fires on (engine.py:1588 sets `token_budget = max(2000, int(source_tokens * 0.20))` so as soon as source >2000, token_budget hits 4000 and max_tokens hits 8000). Input truncation to 3000 alone does NOT fit 3000 + 150 + 8000 = 11150 ≫ 4096. The patch must cap output to `max(100, n_ctx - input - overhead)` not just truncate input.
2. **No tiktoken in gateway venv (verified live).** `count_tokens` falls back to `chars/4` heuristic in production. The pre-flight trigger can false-negative on dense CJK text. Need a secondary chars-based bound (`len(text) > 4 × input_budget`).
3. **Token budget: 3000 not 3500.** Two independent derivations agree: GLM measured ~3180 used (prompt + overhead + Qwen chat template), and `lcm_recover.py:191` independently chose 3000. 3000 leaves ~946 for output.
4. **Config knob, not hardcoded param.** Add `LCM_SUMMARY_MAX_INPUT_TOKENS` and `LCM_SUMMARY_CTX_TOKENS` env vars via the existing `_EnvFieldSpec` pattern (config.py:311-369) so values can be tuned without code changes.
5. **Marker strings must NOT overlap with L3 predicate.** `lcm_recover.py:26` uses `LIKE '%deterministic truncation%'` to find the L3 set. The new input-marker wording "[...input head/tail truncation...]" does NOT contain "deterministic truncation" — keep it that way. Add a regression test.

**Decision (proposed).** Revise Phase 2.5 patch v2 (in fork `hermes-lcm-phase25/`, commit pending):

- `_DEFAULT_LLM_INPUT_TOKENS = 3000` (was 3500 in v1).
- Add `_DEFAULT_LLM_CTX_TOKENS = 4096` and `_DEFAULT_PROMPT_OVERHEAD_TOKENS = 150`.
- Add two `_EnvFieldSpec` entries: `summary_max_input_tokens`/`LCM_SUMMARY_MAX_INPUT_TOKENS` and `summary_ctx_tokens`/`LCM_SUMMARY_CTX_TOKENS`; wire through `hermes-lcm/config.py:602-611`.
- In `summarize_with_escalation`: pre-flight guard uses BOTH `count_tokens(text) > llm_input_tokens` AND `len(text) > 4 * llm_input_tokens` as triggers; pass `max_output_tokens = max(100, llm_ctx - llm_input - prompt_overhead)` to `_invoke_summary_llm_chain` instead of `token_budget * 2`.
- Update both engine.py call sites (1588-1612 leaf-summarize, 5508-5528 rollup-summarize) to pass `llm_input_tokens=self._config.summary_max_input_tokens, llm_ctx_tokens=self._config.summary_ctx_tokens`.
- Add `--plugin-dir` flag and `LCM_PLUGIN_DIR` env var to `lcm_recover.py` so the recovery script follows the symlink (else it tests the OLD escalation.py while the gateway runs the NEW one).

**Deploy mechanism (channel B — symlink flip):**
```bash
mv ~/.hermes/plugins/hermes-lcm{,.disabled} && \
  ln -s /home/hermes-pi/projects/hermes-lcm-phase25 ~/.hermes/plugins/hermes-lcm && \
  systemctl --user restart hermes-gateway && \
  bash /home/hermes-pi/projects/lcm-hygiene/scripts/verify.sh --phase post-restart
```
Rollback: `mv ~/.hermes/plugins/hermes-lcm{.disabled,}` + restart. Symlink mechanism confirmed by GLM-5.2 (gateway unit has no PYTHONPATH; resolves plugins via `~/.hermes/plugins/`).

**Post-flip proof (must run BEFORE Phase 3):**
```bash
LCM_PLUGIN_DIR=/home/hermes-pi/projects/hermes-lcm-phase25 \
  /home/hermes-pi/.hermes/hermes-agent/venv/bin/python -c "
import importlib.util as iu
s = iu.spec_from_file_location('p', '/home/hermes-pi/projects/hermes-lcm-phase25/escalation.py')
m = iu.module_from_spec(s); s.loader.exec_module(m)
assert hasattr(m, '_INPUT_TRUNCATION_MARKER'), 'v2 patch missing'
assert m._DEFAULT_LLM_INPUT_TOKENS == 3000
print('gateway loads v2 patch OK')
"
```

**Alternatives rejected.**
- (a) Increase n_ctx on llama-server — would break all in-flight mlock'd contexts (host memory constraint; M1 boundary).
- (b) Switch to a larger summary model (e.g., Qwen2.5-1.5B) — not loaded on this host; would require model download and additional VRAM; out of scope for Phase 2.5.
- (c) Just bump the input cap to 4000 and accept context overflow — capacity-class failures recur.

**Evidence.** GLM-5.2 verdict transcript: `/home/hermes-pi/.hermes/cache/delegation/subagent-summary-0-20260825_230702_945871.txt`; Codex v1 synthesis: `evidence/codex-synthesis-phase25-20260825_205721.txt`; engine.py call sites verified at `hermes-lcm-phase25/engine.py:1588`, `:5508`; n_ctx verified via llama-server `/props`.

**Revisit condition.** If Phase 3 dry-run on the 137 capacity-fit + 7 boundary-25 nodes produces summaries that don't degrade quality, accept Phase 2.5 as-is. If quality degrades measurably (e.g., summary length drops more than 30% from current 3500-budget behavior), revisit the 3000 default and consider raising n_ctx instead.

---

## 2026-08-26-12 — Accept MID/LARGE remaining (decision A); no further live recovery — accepted

**Context.** R0 live classify 2026-08-26 17:38 CEST (`evidence/r0-classify-2026-08-26.md`): L3 phrase=680, stub=418, phrase_hit=262, **true_marker=0**, FIT residue `true_marker ∩ fit≤3000 ∩ has_src = []`. Morning live FIT recovery already landed (`c36a57a`). Codex review `01a03ebb-e0ca-76f1-aef4-382be5beb609` SHIP-A-WITH-EDITS, 0 blockers.

**Decision.** Close remaining truncation work as **accept MID and LARGE**. Docs-only. Do not run `lcm_recover.py --live`. Do not extend the 3000-token guard this session (needs gateway restart). Do not start a bigger-context model (mlock / Event A).

**Why not B/C/D.** `lcm_recover.py` selects `LIKE` the truncation phrase + nonempty `source_ids` + `NOT LIKE '[stub-recovery%'` (`scripts/lcm_recover.py:38-44`). Widening `--max-source-tokens` reprocesses phrase-hits (1744-class), it does not restore MID/LARGE tails. C/D need restart or extra mlock; host ~400 Mi free.

**Evidence.** `evidence/r0-classify-2026-08-26.md`, `evidence/r1-mid-decision-plan-v1.md`, `evidence/codex-r1-mid-decision-2026-08-26.txt`.

**Revisit condition.** Operator explicitly authorizes a restart knowing free RAM, or a bigger-context summarizer is already running on 8080 without a new mlock.

---
## 2026-08-26 — Truncation plan: accept MID/LARGE (zero-diff)

Delegation deleg_33e1e77b: Codex SHIP-AS-PLANNED (accept LARGE, zero-diff) + GLM SHIP-AS-IS. See evidence/lcm-truncation-decision-2026-08-26.md.

Replay: When MID/LARGE truncation occurs on n_ctx=4096, accept deterministic L3 (recoverable via lcm_expand) because the pre-flight guard (3000/4096, max_output 946) correctly never fired post-flip (0 input-trunc rows) while 63/80 post-flip L3 are FIT under budget and driven by `Qwen2.5-0.5B` circuit-breaker — so enlarging the guard or swapping models saves ≤3 nodes at host-destabilizing cost (5.7G swap, hermes-llama@8081 failed).

Deferred: model retire (Phi-4-mini → Qwen3-4B) stays DRAFT; any future lever is circuit investigation, not token threshold.

