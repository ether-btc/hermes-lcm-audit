# LCM Silent Truncation — Independent Verification

**Date:** 2026-08-25 (CEST, UTC+02:00)
**Author:** Hermes Agent (independent verification of `compression-30s-warning-3-model-review-2026-08-25.md`)
**Status:** VERIFIED — concur with the third model's finding, with sharper measured scope.
**Severity:** Correctness issue, not quality-of-life. Live as of verification time.

---

## Verdict

**Concur.** The third model's claim is correct and, if anything, understated in one respect: 203 of the corrupted summary nodes have **empty `source_ids`**, so they are *permanently lossy* (not merely degraded distillation). The outputs are well-formed and correctly token-counted, so every shape/ratio check passes — the "lie" is that deterministic head/tail truncation is stored and indexed as if it were a real summary.

---

## How it was verified (not taken at face value)

1. **Mechanism (source):** `plugins/hermes-lcm/escalation.py:545-607` `summarize_with_escalation` → L1 (LLM detailed) → L2 (LLM bullets) → L3 (`_deterministic_truncate`, lines 502-542). When the summary-route circuit breaker is open, L1/L2 return `None` and L3 is silently stored as the summary node. L3 keeps head+tail of raw text with marker `[...deterministic truncation — details available via lcm_expand...]`. No error raised.
2. **Incident log (live):** `~/.hermes/logs/gateway.log` shows the circuit opening repeatedly on `custom:llama-cpp/Qwen2.5-0.5B-Instruct-Q4_K_M` and the L3 cascade firing as recently as **2026-08-25 20:18:41** (minutes before this session). `LCM leaf compaction finished in 165987.8ms` logged as success.
3. **Database (live):** quantified below directly from `~/.hermes/lcm.db`.
4. **Content inspection:** pulled sample L3 nodes — verbatim raw tool calls/results, not synthesized summaries. Contrasted with real distilled nodes (e.g. node 1691: proper "Decision:/Command used:" bullets).
5. **Recoverability:** checked `source_ids` retention on L3 nodes.

---

## Measured findings (from `lcm.db`, 1,159 summary nodes total)

| Metric | Value |
|---|---|
| Total summary nodes | 1,159 |
| Nodes containing L3 truncation marker | **608 (52.4%)** |
| L3 damage date range | 2026-05-27 → 2026-08-25 (live) |
| L3 on Aug 22 / 23 / 24 / 25 | 74% / 72% / 70%+ / ~74% of daily nodes |
| L3 by depth (all time) | d0: 548/917 · d1: 43/131 · d2: 14/91 · d3: 3/20 |
| Depth≥1 nodes built ON TOP of truncated leaves | **73** (corruption propagated up DAG) |
| L3 nodes WITH non-empty `source_ids` (recoverable via `lcm_expand`) | **405** |
| L3 nodes WITH empty `source_ids` (permanently lossy) | **203** |

---

## Downstream impact (confirmed in-system)

- **LCM recall / semantic search** indexes `summary_nodes.summary` text. For 52% of nodes that text is head/tail fragments → recall of those conversations degraded to surviving fragments.
- **Condensation** inherited the gap (73 depth≥1 nodes built on truncated leaves).
- **Mnemosyne sleep-time consolidation:** NOT yet traced. Open question: does Mnemosyne read `summary_nodes` or raw `messages` rows? Proven impact is LCM recall + condensation only; Mnemosyne read-path needs one more trace before claiming the memory store is poisoned.

---

## What was NOT done

- Option C (three config edits from the parent audit) was **not applied** — assessment only, owner decision pending.
- Live misconfiguration still in effect: `leaf_chunk_tokens=20000` default (env override `LCM_LEAF_CHUNK_TOKENS` not applied); `LCM_SUMMARY_TIMEOUT_MS=45000` still > hygiene fence.

---

## Decision options (owner)

- **(c) Stop the bleed first:** apply Option C — `compression.hygiene_timeout_seconds: 120` (hot-reload), `LCM_LEAF_CHUNK_TOKENS=2000` (gateway restart), fix config.yaml Frankenstein model name (hot-reload). Reversible.
- **(a) Inspect the 203 unrecoverable nodes** to see what's actually gone.
- **(b) Re-summarize the 405 recoverable nodes** from their `source_ids` via `lcm_expand`.
- Recommended order: (c) → (a) → (b).

---

## Terminal reference (continue from here)

```bash
DB=~/.hermes/lcm.db

# Count L3-truncated summary nodes live (any time)
sqlite3 "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%';"

# Per-day breakdown (total vs L3)
sqlite3 "$DB" "SELECT date(datetime(created_at,'unixepoch','localtime')) d, count(*) total, sum(CASE WHEN summary LIKE '%deterministic truncation%' THEN 1 ELSE 0 END) l3 FROM summary_nodes GROUP BY d ORDER BY d DESC LIMIT 14;"

# Unrecoverable (empty source_ids) vs recoverable
sqlite3 "$DB" "SELECT 'unrecoverable', count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND (source_ids='[]' OR source_ids IS NULL OR source_ids='') UNION ALL SELECT 'recoverable', count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND source_ids<>'[]';"

# Live incident log tail
grep -n -E "circuit opened|skipped by open circuit|LCM leaf compaction finished|hygiene" ~/.hermes/logs/gateway.log | tail -40

# Inspect one L3 node's full content + source_ids
sqlite3 "$DB" "SELECT node_id, source_ids, summary FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' ORDER BY created_at DESC LIMIT 1;"
```

Parent audit: `compression-30s-warning-3-model-review-2026-08-25.md` (same `audits/` dir).
Session context: `@session:default/20260825_202933_6668d6d7`
