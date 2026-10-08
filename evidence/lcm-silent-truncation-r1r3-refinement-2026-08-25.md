# LCM Silent Truncation — Plan Refinement (R1 + R3)

**Date:** 2026-08-25 (CEST, UTC+02:00)
**Author:** Hermes Agent (integrator/verifier, post-plan self-review)
**Inputs reviewed:**
- `compression-30s-warning-3-model-review-2026-08-25.md` (R3 — parent audit, by Codex)
- `lcm-silent-truncation-verification-2026-08-25.md` (R1 — independent verification, by Hermes)
- Live state: `~/.hermes/lcm.db` (811 MB, 1159 nodes), `~/.hermes/config.yaml` (13420 B), `~/.config/hermes-gateway.env`, hermes-agent + hermes-lcm source trees
**Verdict:** Plan is **directionally right** (stop bleed, then recover), but **Edit 1 must be replaced** — the audit's proposed YAML key does not exist in the codebase and would silently no-op. Refined plan below.

---

## R1 — Over-engineering / evidence-quality review

The parent audit is a **3-model review artifact** with strong directional findings, but its evidence ledger contains **~6 of 13 line citations that do not match the current source**. Each was verified mechanically this turn (grep + read_file). This matters because the previous plan (and Option C itself) was built on those citations.

### Citation audit (R1 findings)

| Audit citation | Audit claim | Reality | Severity |
|---|---|---|---|
| `agent/conversation_compression.py:719` | `DEFAULT_CONTEXT_TIMEOUT_SECONDS = 120.0` | **Symbol does not exist** in the 802-line file (grep returns zero). The file contains neither this constant nor any `_TIMEOUT_SECONDS = 120` line. | **CRITICAL** — drives Edit 1 design |
| `compression.hygiene_timeout_seconds` (YAML key) | Hot-reloads per hygiene run | **Key does not exist anywhere** in hermes-agent or hermes-lcm. `grep -rn hygiene_timeout_seconds` returns zero. The actual hygiene timeout is **not configurable** — it is `_HARD_MSG_LIMIT = 400` (hard message cap) plus `_hyg_threshold_pct = 0.85` (95% warn threshold), both hardcoded at `gateway/run.py:7947` / `7984`. | **CRITICAL** — Edit 1 as written is a no-op |
| `agent/conversation_compression.py:1733-1743` | 64K guard rejecting undersized contexts | File only has 802 lines. Actual 64K guard is at lines **154-170**: `if aux_context and aux_context < MINIMUM_CONTEXT_LENGTH`. | MEDIUM |
| `agent/conversation_compression.py:2996-3022` | `touch_progress` wired (native only) | File only has 802 lines. Symbol not at cited location. | LOW |
| `agent/model_metadata.py:413` | `MINIMUM_CONTEXT_LENGTH = 64_000` | Actual line is **133**. | LOW |
| `gateway/run.py:19463` | Hot-reload of hygiene config | File has 15948 lines. Actual hygiene-config read is at **line 7984** (`_raw_hard_limit = _comp_cfg.get("hygiene_hard_message_limit")`). | LOW |
| `gateway/run.py:3652` | `_load_gateway_config` | Actual line is **1591**. | LOW |
| `gateway/run.py:19893-19901` | "Run /compress to retry" user-facing warning | Actual location is lines **8170-8200**, warning string at **line 8185**. | LOW |
| `plugins/hermes-lcm/config.py:585-587` | Circuit breaker: **4 failures**, 300s cooldown | Actual: `failure_threshold: int = 2`, `cooldown_seconds: int = 300`. **Threshold is 2, not 4.** | MEDIUM — affects circuit dynamics |
| `plugins/hermes-lcm/__init__.py:512` | LCM entry into Hermes compressor | Line 512 is `active_engine = kwargs.get("context_compressor")`. Actual register-as-engine is at **line 348**. | LOW |
| `plugins/hermes-lcm/escalation.py:545-607` | `summarize_with_escalation` | **Verified correct.** | OK |
| `plugins/hermes-lcm/escalation.py:502-542` | `_deterministic_truncate` | **Verified correct.** | OK |
| `plugins/hermes-lcm/escalation.py:604-606` | L3 deterministic truncation fallback | **Verified correct.** | OK |
| `plugins/hermes-lcm/escalation.py:229-256` | `_call_llm_for_summary` | **Verified correct.** | OK |
| `plugins/hermes-lcm/escalation.py:387-392` | Spend guard | **Verified correct.** | OK |
| `plugins/hermes-lcm/config.py:202` | `_SUPPORTED_LCM_CONFIG_YAML_KEYS = {"context_threshold"}` | **Verified correct.** | OK |
| `plugins/hermes-lcm/engine.py:1559` | Rescue-shrink floor at `leaf_chunk_tokens` | **Verified correct** (`floor_tokens = max(1, self._config.leaf_chunk_tokens)`). | OK |

### What the audit got right (mechanism, not citations)

The **mechanism** is correct: when L1/L2 summary calls fail and the circuit breaker opens, `summarize_with_escalation` falls through to `escalation.py:604-606` `_deterministic_truncate(...)` and that truncated text is stored as the `summary` column of a real `summary_nodes` row. The `_L3_TRUNCATION_MARKER = "\n\n[...deterministic truncation — details available via lcm_expand...]\n\n"` (escalation.py:460) is what the SQL `LIKE '%deterministic truncation%'` query matches. The `source_ids` column is populated only when the L3 path captured the parent message refs before truncation; when the call short-circuited, `source_ids='[]'` is the default per the table schema (`summary_nodes.source_ids TEXT NOT NULL DEFAULT '[]'`).

The 608 / 405 / 203 split is correct and live (re-verified this turn: 1159 / 608 / 405 / 203 — all unchanged since the original verification).

---

## R3 — Integration / cross-system check

Before refining the plan, three integration questions had to be answered.

### Q1. Is the LCM plugin actually loaded at runtime?
**Yes.** `/home/hermes-pi/.hermes/plugins/hermes-lcm/` exists (54401-byte `adaptive_retrieval.py`, etc., mtime 2026-08-13). `~/.config/hermes/plugins/hermes-lcm/` is a separate plugin copy. The gateway has been using LCM as `context.engine`.

### Q2. What is the live config vs the audit's claims?

Live `~/.config/hermes-gateway.env`:
```
LCM_SUMMARY_MODEL=custom:llama-cpp/Qwen2.5-0.5B-Instruct-Q4_K_M
LCM_SUMMARY_TIMEOUT_MS=45000
LCM_SUMMARY_SPEND_MAX_CALLS=24
LCM_SUMMARY_SPEND_WINDOW_SECONDS=600
LCM_SUMMARY_SPEND_BACKOFF_SECONDS=1800
LCM_LEAF_CHUNK_TOKENS not set (default applies)
```

Live `~/.hermes/config.yaml:88-114` `compression:` + `auxiliary:` blocks: **no `hygiene_timeout_seconds` key, no `timeout` under `auxiliary.compression`, only top-level `terminal.timeout: 180`**. `auxiliary.compression.model: custom:llama-cpp/Qwen3-0.6B-Instruct-Q8_0` — confirmed Frankenstein route. The audit's Edit 3 is correct; the audit's Edit 1 is invalid against this schema.

The actual timeout chain for LCM summary calls:
- Default: `summary_timeout_ms: int = 60_000` (`config.py:600`)
- Override chain: env `LCM_SUMMARY_TIMEOUT_MS` → config.yaml `auxiliary.compression.timeout` (seconds → ms) → default
- Live value: `LCM_SUMMARY_TIMEOUT_MS=45000` (env wins)

The actual hygiene trigger (no timeout — different mechanism):
- `_hyg_threshold_pct = 0.85` hardcoded at `gateway/run.py:7947`
- `_HARD_MSG_LIMIT` from `compression.hygiene_hard_message_limit` (default 400) at line 7984
- `_compress_token_threshold = int(_hyg_context_length * _hyg_threshold_pct)` at line 8044
- After threshold is hit, hygiene calls the agent's compressor; if the compressor's LCM call exceeds `LCM_SUMMARY_TIMEOUT_MS`, the call times out and hygiene surfaces the "Run /compress to retry" warning (line 8185)

**The 30s-vs-45s mismatch the parent audit identified is real**, but it is not a hygiene timeout — it is that the hygiene loop fires repeatedly while a single summary call is still in-flight. The fix is **not** a hygiene timeout knob (which doesn't exist). The fix is either:
(a) shrink the per-call timeout so the call fails fast and hygiene surfaces sooner (45s → 30s is wrong direction; should be **larger** so the call completes before hygiene retires), OR
(b) raise `LCM_SUMMARY_TIMEOUT_MS` to give the call room to complete (matches the audit's intuition but at the wrong knob), OR
(c) shrink `LCM_LEAF_CHUNK_TOKENS` so each L1/L2 call has a smaller prompt and completes well under timeout — this is what Edit 2 does, and is the right answer.

### Q3. Live samples of the 203 / 405 buckets confirm the audit's claim

Sample from unrecoverable bucket (203): node 710 — `source_ids=[]`, `summary=` raw `[TOOL RESULT]`/`[ASSISTANT]` text head/tail. The text is raw conversation fragments with no summary framing. No way to recover because there are no source message IDs to expand.

Sample from recoverable bucket (405): node 1705 — `source_ids=[259667, ..., 259676, ...]`, `summary=` raw tool-call fragments. The `lcm_expand(source_ids=...)` path will reconstruct the raw conversation, which can then be re-fed through L1/L2 to produce a real summary, replacing the L3 row.

Both samples confirm the audit's verdict is correct: the 203 are permanently lossy text, the 405 are recoverable structurally.

---

## Refined plan (c → a → b, with Edit 1 replaced)

### Edit 1 (REPLACED) — raise summary timeout so L1/L2 completes before circuit opens

The audit proposed adding `compression.hygiene_timeout_seconds: 120`. That key does not exist. The real fix is to raise `LCM_SUMMARY_TIMEOUT_MS` in `~/.config/hermes-gateway.env` so each L1/L2 call has enough room to finish against the local Qwen2.5-0.5B on `:8080` (which the audit confirmed is `n_ctx=4096`). Currently `LCM_SUMMARY_TIMEOUT_MS=45000`. The audit's intent was "single healthy-but-slow call shouldn't trip hygiene." Raising to **90000–120000** gives L1/L2 twice the room. Trade-off: longer recovery from a hung call.

**Decision (R3):** keep the env knob as the lever (not the phantom YAML key). Recommend `LCM_SUMMARY_TIMEOUT_MS=90000` — matches the audit's "120" precedent without inventing a config path that doesn't exist.

```
# ~/.config/hermes-gateway.env — change:
LCM_SUMMARY_TIMEOUT_MS=90000
```

Then `systemctl --user restart hermes-gateway` (this becomes Edit 1; no hot-reload path; harmless restart).

### Edit 2 — shrink leaf chunks (UNCHANGED, hot via env + restart)

`LCM_LEAF_CHUNK_TOKENS=2000` in `~/.config/hermes-gateway.env` (was 20000 default). Combined with Edit 1's longer timeout, each L1/L2 call now has (a) a smaller prompt (fits 4K context) and (b) more wall-clock to finish. The two together address both legs of the "exceeds the available context size" 400 plus the timeout cascade.

Then `systemctl --user restart hermes-gateway` (Edit 1 and Edit 2 land in the same restart — combine into a single maintenance step).

### Edit 3 — fix Frankenstein route (UNCHANGED, hot-reload)

`~/.hermes/config.yaml:111`: change `auxiliary.compression.model` from `custom:llama-cpp/Qwen3-0.6B-Instruct-Q8_0` to `custom:llama-cpp/Qwen2.5-0.5B-Instruct-Q4_K_M` (match the env's `LCM_SUMMARY_MODEL`). Bookkeeping today, prevents the latent 64K-guard rejection if the env override ever drops.

Hot-reload (gateway reads `_comp_cfg` on each hygiene run via `gateway/run.py:7984`'s `_raw_hard_limit = _comp_cfg.get("hygiene_hard_message_limit")` pattern).

### Verification gate (NEW, before restart)

T-V: Run the 5-step verification from `lcm-silent-truncation-verification-2026-08-25.md` against the live DB. Capture: timestamp, total nodes, L3 count, recoverable/lossy split. Save to `hermes-vault/audits/lcm-state-snapshot-pre-restart-<ts>.md`. This anchors the "before" state so the "after" comparison is honest. Re-verify after restart and after 2-3 long sessions.

### Recovery (T6, T7) — unchanged intent, refined approach

T6: Pull inventory of the 203 unrecoverable nodes (date buckets, depth distribution, sample text). Filed artifact: `hermes-vault/audits/lcm-lossy-inventory-2026-08-25.md`. Goal: characterize, not recover.

T7: Re-summarize the 405 via `lcm_expand(source_ids=...)` → reconstruct raw → L1/L2 → UPDATE the row's `summary` and `token_count` (NOT INSERT — must replace the L3 row to keep node_ids stable for downstream references). Idempotent: skip if the row's `summary` no longer contains the truncation marker (already-fixed rows).

```
UPDATE summary_nodes
SET summary = ?, token_count = ?
WHERE node_id = ?
  AND summary LIKE '%deterministic truncation%';
```

After T7: re-run the L3 count query; expect ≤ noise floor.

### Trace (T8) — UNCHANGED

Trace Mnemosyne sleep-time consolidation: does it read `summary_nodes` or raw `messages`? One read, one verdict, filed as audit addendum.

### Scaffold (T9) — UNCHANGED

Create `hermes-vault/projects/lcm-hygiene/` with README/PRAXIS/ROADMAP/DECISIONS/STATUS + scripts/verify.sh that re-runs the 5-step verification. STATUS.md anchors every numeric claim to the literal command that produced it (per project-planning evidence rule).

---

## Updated milestone definitions (refined)

M1 — **Bleed stopped (T1–T3 + T-V):** Edits 1+2+3 applied, gateway restarted, the L3-with-marker count plateaus at 608 (no growth from new sessions); 2-3 long sessions produce real L1/L2 summaries. Anchor: pre/post L3 count from `lcm-state-snapshot-pre-restart-<ts>.md` vs the live re-check.

M2 — **Loss characterized (T6):** the 203 unrecoverable nodes have an inventory; severity of loss is bounded.

M3 — **Corruption cleared (T7):** the 405 recoverable nodes have been re-summarized; L3-with-source_ids count near zero.

M4 — **Project durable (T8–T9):** Mnemosyne read-path verdict filed; scaffold exists for any future regression; verify.sh exits 0.

---

## Top issues + recommendations

1. **Edit 1 phantom key — must fix before any execution.** Replace with `LCM_SUMMARY_TIMEOUT_MS=90000`. Restart required.
2. **Citations to correct in the parent audit.** Add a "citation corrections" addendum to `compression-30s-warning-3-model-review-2026-08-25.md` so a future reviewer doesn't re-derive the wrong line numbers.
3. **30s hygiene "timeout" is misleading terminology.** Hygiene has no timeout knob; what the audit observed was repeated firing while a single LCM call was in-flight. Fixing the symptom means (a) smaller prompts AND (b) longer per-call timeout, both at the env layer.
4. **Audit framing "30s vs 45s structural inconsistency"** is the right intuition pointed at the wrong knobs. The 30s figure comes from somewhere (likely a default in the LCM harness internal logic; not surfaced as a config knob); the 45s is the env-set LCM timeout. The fix is to raise 45s to 90s — not to add a YAML knob that does not exist.
5. **The 73 depth≥1 nodes built on truncated leaves** (from verification audit) means some condensation loss propagated. T7's UPDATE-based replacement strategy handles those too: the row's source_ids still point to the original messages (or to the L3 leaf), so re-expansion reaches the underlying content.

---

## Verdict

**c → a → b is sound in structure.** The mechanism is real (escalation.py:545-607, 604-606, 502-542, all verified), the live counts are real (608/405/203), and the fix path is reversible in three independent edits. The one critical correction is **Edit 1**: the YAML key `compression.hygiene_timeout_seconds` does not exist in the codebase, and any patch built on that key would be silently no-op'd by Hermes' config loader. The real knob is `LCM_SUMMARY_TIMEOUT_MS`, raised from 45000 to 90000. Everything else (Edit 2, Edit 3, T6, T7, T8, T9) is sound as written.

Confidence: **HIGH** on direction; **HIGH** on Edit 1 fix; **MEDIUM** on whether 90000ms is the right magnitude (might want 60000 if the underlying issue is model speed, not call count) — recommend spike of 1–2 days of post-restart observation to confirm the right number.

---

## Terminal reference

```bash
# State snapshot (pre-restart anchor)
DB=~/.hermes/lcm.db
TS=$(date +%Y%m%d_%H%M%S)
sqlite3 -readonly "$DB" "
  SELECT 'total', count(*) FROM summary_nodes;
  SELECT 'l3', count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%';
  SELECT 'unrecoverable', count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND (source_ids='[]' OR source_ids IS NULL OR source_ids='');
  SELECT 'recoverable', count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND source_ids<>'[]';
" | tee /tmp/lcm-pre-restart-$TS.txt

# Edit 1+2 in env (atomic)
cat >> ~/.config/hermes-gateway.env <<'EOF'
LCM_SUMMARY_TIMEOUT_MS=90000
LCM_LEAF_CHUNK_TOKENS=2000
EOF
systemctl --user restart hermes-gateway
sleep 5
systemctl --user status hermes-gateway --no-pager

# Edit 3 in config.yaml
# (manual patch: line 111, custom:llama-cpp/Qwen3-0.6B-Instruct-Q8_0
#  -> custom:llama-cpp/Qwen2.5-0.5B-Instruct-Q4_K_M)

# Re-verify (post-restart)
sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%';"
# Expect: 608 (or below — should not have grown during restart)

# Re-verify (2-3 long sessions later)
# Same query. Expect: plateaued at 608 or lower.
```

Parent: `compression-30s-warning-3-model-review-2026-08-25.md`
Verification: `lcm-silent-truncation-verification-2026-08-25.md`
Session: `@session:default/20260825_202933_6668d6d7`