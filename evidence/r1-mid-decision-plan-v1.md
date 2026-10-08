# R1 plan v1 — MID/LARGE remaining policy (no code, no live DB write)

Reviewer: Codex, read-only. Do not create or modify any files. Do not run lcm_recover.py. Do not restart anything.

## Decision under review

**Pick A — accept MID and LARGE as out of scope.** File STATUS/wiki/Mnemosyne. Stop.

Not B (recover MID under 3000-cap), not C (extend guard — needs gateway restart), not D (bigger model / extra mlock).

## Why A

1. R0 FIT residue is empty (`true_marker ∩ fit ∩ has_src = []`). Morning live FIT recovery already happened. Widening `--max-source-tokens` would be busywork.
2. Phase 2.5 guard is **designed** to cap at 3000 tokens. MID (3001–8000) still truncates. Recovering MID via `lcm_recover.py --max-source-tokens 8000` only summarizes a head/tail already truncated by the same cap. No lost tail is restored.
3. Host: ~400 Mi free, zram 5.5/8G. C requires gateway restart to load new plugin code. D requires a new mlocked llama-server. Event A (2026-08-26 13:09) was an extra Phi-4 mlock OOM. Forbidden this session unless operator explicitly authorizes a restart knowing RAM.
4. Ponytail: laziest solution that works is document + stop.
5. Five MID not-stub has_src nodes (1762, 1770, 1801, 1820, 1842) are mixed heading summaries and raw assistant dumps that *mention* the truncation phrase. They are not a clean recoverable stub set.

## Explicit non-actions

- No `lcm_recover.py --live` / `--stub`
- No plugin / config / env edit
- No systemd / llama-server restart or kill of PIDs 831, 1113, 1114, 830
- No sqlite write on `~/.hermes/lcm.db`
- No `git add -A` of wiki `log.md` or untracked pxpipe files
- No commit of dirty leftover hygiene scripts (`lcm_recover.py`, `lcm_drift_check.sh`, pyc) as part of this closeout

## Allowed R3 writes after this review (docs only)

- `~/projects/lcm-hygiene/STATUS.md` — stamp now; delete stale “open blockers” that already landed
- wiki `projects/lcm-hygiene-silent-truncation-guard-2026-08.md` only (not dirty log.md)
- Mnemosyne task slots
- This evidence file already written at `evidence/r0-classify-2026-08-26.md`

## Live facts the reviewer must treat as given (re-derived 17:38 CEST)

See `evidence/r0-classify-2026-08-26.md`. L3 phrase=680; true_marker=0; FIT residue=[]; plugin phase25@915bec0; M1 knobs in YAML; 8080 PID 831 is the only LCM summarizer.

## Return format

STRUCTURED REVIEW:
1. BLOCKER — must-fix before filing A
2. IMPROVEMENT
3. SCOPE — is A correctly bounded? Any named node that is actually a FIT true_marker we missed?
4. VERDICT — SHIP-A / SHIP-A-WITH-EDITS / REJECT-A

Cite file:line or SQL class. Do not invent live counts. If you re-query, use `sqlite3 -readonly` only.
