# STATUS — lcm-hygiene

**Last updated:** 2026-08-26 18:01 CEST (UTC+02:00)
**Phase:** remaining work CLOSED as decision A (accept MID/LARGE). Filed to ether-btc/wiki. **GitHub source repo: NOT APPLICABLE** (history contains private live-DB snapshot).
**Mnemosyne task slots:** `lcm-hygiene`, `lcm-hygiene-v21-and-live-run`, `lcm-hygiene-remaining`

Treat this file as current. Older ADRs / EXECUTION-PROMPT.md / compacted summaries that still say “Phase 2.5 pending” or “live write owner-gated” are **stale**. Live symlink + `sqlite3 -readonly` win.

## R0 + R1 close-out (2026-08-26 17:38–17:45)

**R0 classify** (`evidence/r0-classify-2026-08-26.md`, `verify.sh --phase inventory` 4/0/0):

| Class | n |
|---|---|
| L3 phrase `LIKE '%deterministic truncation%'` | 680 |
| stub (`LIKE '%stub-recovery%'`) | 418 |
| phrase_hit (in-body mention, not a stub) | 262 |
| **true_marker** | **0** |
| unrecoverable empty `source_ids` | 203 |
| FIT write-candidates (`true_marker ∩ fit≤3000 ∩ has_src`) | **[]** |

Axis (verify.sh): fit=146, boundary25=8, mid=64, large=462.

Phrase-hit FIT (35) are 2037-char tool-result / heading dumps (node **1744** is this class, not a parked stub). Five MID not-stub has_src nodes (1762, 1770, **1801**, 1820, 1842) are heading/raw summaries under a 3000-token guard — expected. LARGE includes node 1609 (211,781 tokens, stub-shaped, Mode B).

**R1 decision A** — accept MID and LARGE as out of scope. Codex `01a03ebb-e0ca-76f1-aef4-382be5beb609` verdict **SHIP-A-WITH-EDITS**, blockers none (`evidence/codex-r1-mid-decision-2026-08-26.txt`). Controlling basis: global `true_marker=0`, plus `lcm_recover.py` selects broad phrase matches (`LIKE` marker, nonempty `source_ids`, `NOT LIKE '[stub-recovery%'`), so widening `--max-source-tokens` would reprocess phrase-hits, not recover lost tails.

**R2 skipped.** Empty FIT residue. No `lcm_recover.py --live`. No DB write.

## Live facts (re-derived 17:38 CEST)

| Fact | Value |
|---|---|
| plugin | `~/.hermes/plugins/hermes-lcm` → `hermes-lcm-phase25` @ `915bec0` |
| rollback | `.disabled` → `~/projects/hermes-lcm` |
| M1 YAML | `compression.hygiene_timeout_seconds: 120`, `auxiliary.compression.timeout: 90` |
| env | **no** `LCM_SUMMARY_TIMEOUT_MS` |
| 8080 | PID 831, systemd active, Qwen2.5-0.5B n_ctx=4096 — LCM path, **untouched** |
| 8081 | PID 1114 PPID=1, unit failed — **untouched** |
| 8082 | PID 1113 PPID=1 Phi-4, unit disabled — **untouched** (not an LCM blocker) |
| gateway | PID 830 active since 13:20:35 — **untouched** |
| RAM | ~399 Mi free, zram 5.5/8 G |
| hygiene HEAD at classify | `b8ca931` |
| morning live FIT recovery | already in `c36a57a` + drift commits |

## What is done (do not redo)

M1 dual-knob · policy env→YAML · Phase 2.5 v2 symlink flip · Phase 3 dry-run (31 real FIT, 14 would-write / 17 skip) · morning live FIT recovery · R0 classify · R1 accept MID/LARGE.

## Open (not this session)

- v2.1: tighten chars/4 margin (dense-text 400s after scaffolding). Config-only, needs review + likely gateway restart. Owner later.
- Optional bigger-context model for LARGE. Forbidden while free RAM is hundreds of Mi (Event A 13:09 extra mlock OOM). See deferred `~/.hermes/plans/2026-08-26_phi-retire-qwen3-4b-replace.md` — **different project**.
- `lcm_recover.py` selector is phrase-wide; do not treat its candidate count as true_marker count.

## Filing (2026-08-26 18:01)

- Wiki closeout audit: `ether-btc/wiki` `audits/lcm-hygiene-remaining-closeout-2026-08-26.md`
- Codex filing review: `01a03ecc-c154-7220-a7d9-a430c9f12125` (do not create GitHub source repo)
- Local `.gitignore` added as **future-copy prevention** only. History still contains `evidence/backups/lcm-pre-recovery-20260826.sqlite3` from `8b2529e` (827592704 bytes). **Do not add a remote or push until a separately authorized history-purge/rebuild project is completed.**
- Leftover `scripts/lcm_recover.py` + drift/dryrun dirt left uncommitted (code, not filing).

## Hard stops (still)

No gateway/llama restart. No second mlocked llama-server. No live `lcm.db` write without `--backup --confirm-live --local-only` + review + operator go. No `git add -A` of wiki `log.md`. No `gh repo create` / `git remote add` while the sqlite blob is in history.
