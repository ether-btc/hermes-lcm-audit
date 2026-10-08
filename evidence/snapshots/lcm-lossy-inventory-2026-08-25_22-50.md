# LCM Lossy-Node Classified Inventory — 2026-08-25 22:50 UTC

**Why this exists:** Per independent reviewer verdict (GLM-5.2, 2026-08-25 22:49, subagent id `sa-0-9d70a4f7`), the observation window must be redefined with cause classification. This inventory sizes the **capacity-mode blast radius** (how many L3 nodes are too large to fit n_ctx=4096) and produces the Phase 3 scope baseline.

**Method:** read-only SQLite query against `~/.hermes/lcm.db` (no writes, no backup needed).

## Headline counts

```
DB: /home/hermes-pi/.hermes/lcm.db
captured: 2026-08-25T20:50:59Z
total summary_nodes: 1217
total L3 (truncated): 651
  recoverable (source_ids != '[]'): 448
  unrecoverable (source_ids == '[]'): 203
```

The 651 vs the 649 in earlier evidence reflects: (a) the drift check at 22:45 added node 1760, and (b) one additional marker appeared between 22:45 and 22:50. **Live total continues to grow.** A follow-up drift check should run every ~5 min during long sessions.

## Classification by depth × source_token_count bucket

Bucket thresholds: ≤3500 = "capacity-fit" (Qwen2.5-0.5B n_ctx=4096 minus output reserve); 3501-8000 = mid-overflow; >8000 = large-overflow.

| depth | capacity-fit | mid-overflow (3501-8000) | large-overflow (>8000) | row total |
|------:|-------------:|----------------------:|----------------------:|----------:|
| 0     | 61           | 60                    | **446**               | 567       |
| 1     | 57           | 1                     | 0                     | 58        |
| 2     | 22           | 0                     | 0                     | 22        |
| 3     | 4            | 0                     | 0                     | 4         |
| **TOTAL** | **144**  | **61**                | **446**               | **651**   |

## Interpretation

**506 of 651 (78%) lossy nodes are capacity-overflow** — they could NEVER have been summarized by Qwen2.5-0.5B at n_ctx=4096, regardless of timeout. The original failure-mode hypothesis ("M1 fixes silent truncation via timeout raise") was correct only for the 144 capacity-fit nodes; the 506 overflow nodes represent a **separate, larger failure mode** that was always latent.

This changes the recovery scope:
- **Capacity-fit (144 nodes)**: M1's timeout raise + 90s budget makes these potentially recoverable. Phase 3 candidate list.
- **Mid-overflow (61 nodes)**: input 3501-8000 tokens = still 1-2× n_ctx. Could be recovered with a head/tail pre-trim guard that fits within n_ctx.
- **Large-overflow (446 nodes)**: input 8K-200K tokens. Cannot be recovered with Qwen2.5-0.5B at all. Requires either (a) a larger-context model on the host (none exists), (b) a chunk-and-stitch pipeline (fragile, may produce incoherent summaries), or (c) accepting permanent loss.

## Top 10 largest nodes (all depth=0, all 79K-211K source tokens)

```
node=1609 stc=211,781  ← 51× n_ctx
node=281  stc=186,675
node=267  stc=113,828
node=393  stc=113,420
node=246  stc=108,637
node=1135 stc=93,854
node=1133 stc=93,797
node=1564 stc=87,672
node=899  stc=83,850
node=1607 stc=79,923
```

All 10 have source_ids populated, so they're "recoverable" in the script's filter sense — but recovering them with the current model is impossible. They would have to be flagged `unrecoverable=true` semantically even though the script's filter marks them recoverable.

## What this means for M1

**M1 still does useful work** — it (a) raised the gateway idle fence from 30s to 120s and (b) raised the LCM call budget from 60s to 90s. For nodes that fit within n_ctx=4096 (the 144 capacity-fit), this may convert some latent silent truncations into successful summaries going forward.

**M1 does NOT fix the 506 overflow nodes.** Those will continue to produce L3 markers as long as the input exceeds n_ctx. M1's TRIGGER-TO-REVERT ("no new timeout-driven markers over 2-3 sessions") will be satisfied vacuously because **almost no new markers will be timeout-driven going forward** — they'll be capacity-driven.

## What this means for Phase 3

The reviewer's sharp edge holds: running `lcm_recover.py --live` against the 448 currently-feedable nodes would call `summarize_with_escalation` on each, fail identically on capacity-overflow nodes, fall through to the local fallback which truncates input to 12K *chars* (about 3-4K tokens) and writes a low-fidelity summary. **This permanently consumes the idempotency predicate** (lcm_recover.py:49-53) on nodes that, post-guard-fix, could have been properly summarized.

**Decision (per reviewer): Phase 3 BLOCKED until input-token guard lands.** The guard must:
1. Sit at the top of `summarize_with_escalation` (`escalation.py:545`), covering both gateway and recovery paths.
2. Use the existing `_truncate_text_to_tokens` machinery (`escalation.py:465`) and head/tail assembler (`escalation.py:519-524`) — ~10 lines of new code.
3. Annotate the truncated result so audits can distinguish "summary of truncated input" from clean summaries.

## What this means for the observation window

The drift-log currently logs only counts. Per reviewer, **redesign the drift log to classify each new L3 node by axis**: log depth + source_token_count, bucketed at 3500 (capacity-fit vs capacity-overflow). This lets us:
- Attribute new markers to capacity-axis (known-unfixed, expected) vs timeout-axis (would trigger M1 revert).
- Detect when the timeout-axis count stops growing (= M1 working).
- Detect when the capacity-axis count keeps growing (= guard urgently needed).

## Action items (in priority order)

1. **Run this inventory script as part of verify.sh** — fast (sub-second), provides Phase 3 scope baseline + capacity-blast-radius every run.
2. **Patch `drift_check.sh`** to log cause classification (depth + stc bucket).
3. **Land input-token guard at `escalation.py:545`** (hermes-lcm repo, separate project — file as PR/issue there).
4. **Migrate env `LCM_SUMMARY_TIMEOUT_MS=90000` → `auxiliary.compression.timeout: 90` in YAML** (atomic edit; verify.sh check updated in same commit).
5. **Add safety gates to `lcm_recover.py`**: --confirm-live flag + refuse --live/--stub on live DB without same-session backup.

## Cite-able claims (one-line each)

- 78% of L3 markers are capacity-overflow: this inventory.
- M1 still helps for capacity-fit nodes: this inventory + M1 application record.
- Phase 3 must wait for input-guard: independent reviewer verdict + this inventory.
- Drift log needs cause classification: independent reviewer verdict.
- env→YAML migration is atomic (env wins on precedence): hermes-lcm/config.py:837-841.