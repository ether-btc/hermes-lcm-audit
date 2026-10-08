# FRESH SESSION — remaining LCM truncation (not a restart of M1 / 2.5 / Phase 3)

You are a new Hermes session. Compacted summaries, STATUS.md, the wiki page, and `EXECUTION-PROMPT.md` are **stale in different directions**. Live files and `sqlite3 -readonly` win. Do not resume M1, Phase 2.5 deploy, Phase 3 dry-run, or the 2026-08-26 morning live FIT recovery. Those already happened.

Success (one sentence): remaining lossy LCM summaries are either recovered under the existing gates or explicitly accepted as out-of-scope, with STATUS/wiki/Mnemosyne matching a live classified inventory, and with zero restarts and zero unreviewed writes to `lcm.db` or plugin/config.

---

## Host hard stops (permanent this session)

Do **not**:

- restart `hermes-gateway`, any `hermes-llama@*`, or any `llama-server`
- `kill` / replace PID 831 (8080 Qwen2.5-0.5B — LCM summarizer), 1114 (8081 Qwen3-0.6B), 1113 (8082 Phi-4)
- start a second mlocked llama-server (Event A 2026-08-26 13:09: extra Phi on 8082 OOM-killed the host)
- edit `~/.hermes/config.yaml` or `~/.config/hermes-gateway.env`
- flip or retarget `~/.hermes/plugins/hermes-lcm`
- `sqlite3` without `-readonly` on `~/.hermes/lcm.db`
- run `lcm_recover.py --live` / `--stub` against the live DB without same-session `--backup` + `--confirm-live` + `--local-only` + Codex review + operator go
- rebuild, merge, or “fix” PROMPRO / RTK / phi-retire while doing this
- treat `LIKE '%deterministic truncation%'` as the recoverable set

Host memory at last probe (2026-08-26 17:26 CEST): ~0.4 Gi free, zram ~5.5/8 Gi. Extra mlock is a reboot.

Phi-4 on 8082 is **not** an LCM blocker. LCM summarizes via **127.0.0.1:8080**. PID 1113 is an orphan (`PPID=1`); `hermes-llama@8082` is disabled/inactive. Leave it. Phi→Qwen3-4B is a **different** deferred plan (`~/.hermes/plans/2026-08-26_phi-retire-qwen3-4b-replace.md`). Out of scope.

---

## What is already done (do not redo)

Verify each claim with a command. If live state matches, skip that phase.

| Claim | How to verify | If true |
|---|---|---|
| M1 dual-knob timeout | `rg -n 'hygiene_timeout_seconds|auxiliary.compression.timeout' ~/.hermes/config.yaml`; env must **not** set `LCM_SUMMARY_TIMEOUT_MS` | skip timeout work |
| Phase 2.5 guard live | `readlink -f ~/.hermes/plugins/hermes-lcm` = `/home/hermes-pi/projects/hermes-lcm-phase25`; git HEAD there was `915bec0` | skip deploy / symlink flip |
| Rollback still possible | `~/.hermes/plugins/hermes-lcm.disabled` → `/home/hermes-pi/projects/hermes-lcm` | do not flip unless operator says rollback |
| Phase 3 dry-run | `~/projects/lcm-hygiene/evidence/phase3-dryrun-full.log` exists; ROADMAP says 31 real FIT nodes, 14 would-write / 17 skip, exit 0 | skip dry-run |
| Morning live FIT recovery | task `lcm-hygiene-v21-and-live-run`; hygiene HEAD was `b8ca931` | do not re-run FIT `--live` blindly |
| OpenRouter aux is dead by choice | user will not top up; standalone recovery **must** `--local-only` | never call OpenRouter for this |

Stale-on-purpose files (do not follow “next action” in them):

- `~/projects/lcm-hygiene/STATUS.md` last stamp **08:15 CEST** still lists Phase 2.5 / policy migration / safety gates as owner-blocked. All three landed later that day.
- `~/projects/lcm-hygiene/EXECUTION-PROMPT.md` is the **M1-era** resume. Ignore its mission.
- Wiki `projects/lcm-hygiene-silent-truncation-guard-2026-08.md` still says live write is owner-gated; morning run already wrote.

Authoritative **code/docs to read after the live probe**, not before:

1. `~/projects/lcm-hygiene/scripts/lcm_recover.py` (`--help` first)
2. `~/projects/lcm-hygiene/scripts/verify.sh` and `scripts/lcm_drift_check.sh`
3. `~/.hermes/skills/hermes-lcm/references/silent-truncation.md` (Mode A vs Mode B)
4. `~/projects/lcm-hygiene/DECISIONS.md` ADRs 05, 09, 10, 11
5. Latest drift lines in `~/projects/lcm-hygiene/evidence/drift-log.txt`

Skills this session: `hermes-lcm`, `ponytail`, `gated-change-workflow`, `session-continuation` (Bank 7 on llama PIDs), `codex` for any write. Independent review before any plan that touches config, plugin, or live DB. You are SWE lead; operator is CEO — do not ask them to re-decide finished items.

---

## Live snapshot at prompt authoring (2026-08-26 17:26 CEST)

Re-derive. These numbers **will have moved**.

```
L3 LIKE '%deterministic truncation%' = 680
  recoverable (source_ids not empty) = 477
  unrecoverable (empty source_ids)   = 203
  fit<=3000 = 146 | 3001-3500 = 8 | mid 3001-8000 = 64 | large>8000 = 462
8080 PID 831 systemd  Qwen2.5-0.5B  n_ctx=4096  (LCM path — do not touch)
8081 PID 1114 PPID=1  Qwen3-0.6B    (systemd unit failed; process still up)
8082 PID 1113 PPID=1  Phi-4-mini    (unit disabled; orphan — do not touch)
plugin: ~/.hermes/plugins/hermes-lcm -> hermes-lcm-phase25 @ 915bec0
hygiene repo HEAD was b8ca931
```

Known classification bugs you must not repeat:

1. **`[stub-recovery placeholder ...]` does not match `LIKE '%[stub-recovery]%'`** — there is no `]` after `recovery`. Filter with `summary LIKE '%stub-recovery%'` or `summary LIKE '[stub-recovery%'`.
2. **Phrase-in-body false positives.** Node **1744** (stc=569, depth=1) starts as a tool-result JSON dump and is **not** a truncation stub. Confirm with `instr(summary,'deterministic truncation')` before treating any “parked 1744 remediation” as open work.
3. **Node 1801** (stc=4334, MID, session `20260825_204439_e5c9a9`) is the only documented post-23:19 **in-scope** new bleed from the hygiene session itself. Guard cap is 3000; MID 3001–8000 still truncates **by design**.
4. Post-flip growth after 23:19 is mostly LARGE leaves + other-session FIT/MID raw-ish nodes. Do not call that “M1 regression.”
5. Whole-table `MAX` / raw L3 count includes stubs and phrase hits. Window and shape-classify.

Mode A (timeout, depth≥1, stc fits n_ctx) vs Mode B (capacity, stc ≫ 4096): raising timeout does nothing for Mode B. Large bucket (node 1609 = 211,781 tokens) is permanently lossy on 0.5B/4096 unless a bigger-context model exists. It does not, and you will not start one.

---

## Mission (remaining only)

### Phase R0 — live classify (read-only, required)

Run Bank 7 on 8080/8081/8082 (PID, unit, `ppid`, argv, no restart). Then:

```bash
date
readlink -f ~/.hermes/plugins/hermes-lcm
git -C ~/projects/hermes-lcm-phase25 log -1 --oneline
git -C ~/projects/lcm-hygiene log -1 --oneline
free -h; swapon --show
bash ~/projects/lcm-hygiene/scripts/lcm_drift_check.sh
bash ~/projects/lcm-hygiene/scripts/verify.sh --phase inventory
```

Then SQL on `sqlite3 -readonly ~/.hermes/lcm.db` that emits **four disjoint sets**:

1. **stub** — `summary LIKE '%stub-recovery%'`
2. **true_marker** — starts with / is a short deterministic-truncation stub, not (1)
3. **phrase_hit** — body mentions the phrase but is a real heading/raw summary (1744-class)
4. **unrecoverable** — empty `source_ids`

Cross by bucket: fit≤3000, boundary 3001–3500, mid 3001–8000, large>8000.  
Cross by session: current vs cross-session.  
List node_ids for true_marker ∩ fit ∩ has_src. That list is the only FIT write-candidate set.

If that set is empty: FIT recovery is done. Say so. Do not invent more FIT work.

### Phase R1 — decide MID (no write)

MID bleed is expected with a 3000-token guard. Options, pick **one** after Codex read-only review (no `codex exec --readonly` on this host — that flag is rejected; put read-only in the prompt):

- **A. Accept.** Document MID/LARGE as out of scope. File and stop. Default under ponytail + RAM pressure.
- **B. Recover MID under the existing 3000-cap** (`lcm_recover.py --max-source-tokens 8000 --live --local-only …`). Output is a summary of a truncated head/tail, annotated. Does not restore lost tail.
- **C. Extend the guard** (plugin change). Owner-gated, needs review, **and a gateway restart to load new plugin code** — **forbidden this session** unless the operator explicitly authorizes a restart knowing free RAM is ~400 Mi.
- **D. Bigger model for LARGE.** Forbidden this session (mlock / Event A). File as a pointer to the phi-retire plan only.

If unsure, debate Codex + one other model, then take A unless a reviewer shows a safe no-restart path for a **named** node list.

### Phase R2 — optional FIT residue only

If R0 found true_marker ∩ fit ∩ has_src nodes **not** already recovered:

1. Snapshot: `sqlite3 ~/.hermes/lcm.db ".backup /tmp/lcm.db.pre-r2-$(date +%Y%m%d_%H%M%S)"` (this is a SQLite backup; it is the one allowed write-adjacent step, and only after operator go).
2. Spike `--dry-run --local-only --plugin-dir $(readlink -f ~/.hermes/plugins/hermes-lcm) --max-source-tokens 3000 --limit 5`.
3. Codex reviews the exact command line + candidate node_ids.
4. Operator go, then `--live --local-only --confirm-live --backup <that snapshot>`.
5. `verify.sh --phase post-recovery` + drift-check. Integrity check must pass.

Never `--live` without `--local-only`. The standalone aux client resolves `auto` → dead OpenRouter and swallows 402s as fake success.

### Phase R3 — file the truth

Update, do not clobber other sessions’ dirty files:

- `~/projects/lcm-hygiene/STATUS.md` — last-updated now; delete the fake “open blockers”; remaining = R1 decision + any R2 residue
- wiki `projects/lcm-hygiene-silent-truncation-guard-2026-08.md` — live recovery happened; remaining is MID/LARGE policy
- Mnemosyne `mnemosyne_task_progress` on `lcm-hygiene` and `lcm-hygiene-v21-and-live-run`
- append `log.md` / evidence; do not stage unrelated dirty wiki hunks (pxpipe/phi)

No GitHub repo create. Commit hygiene repo + wiki only if the operator already uses that pattern for this project; do not ask them to re-decide a known pattern — recover it from `git log`.

---

## Adversarial inputs (must not fail these)

1. STATUS says “Phase 2.5 deploy pending.” → You re-derive symlink + HEAD. You do not deploy.
2. L3 count is 680, morning note said 659. → You classify. You do not declare M1 failed or re-raise timeouts.
3. Summary says “Phi-4 8082 blocks all LCM hygiene.” → You check 8080. You do not restart 8082.
4. A doc says “next: systemctl --user restart hermes-gateway.” → You refuse. Cold knobs are already set.
5. Someone asks to recover node 1609 / LARGE. → You refuse. Mode B, 51× n_ctx.
6. `lcm_recover.py --live` without `--local-only`. → You refuse.
7. Empty FIT residue. → You file and stop. You do not widen `--max-source-tokens` to keep busy.
8. Wiki `log.md` is dirty from another session. → You do not `git add -A`.

---

## Output shape when you finish

```
LCM-REMAINING
├── live: L3=… stub=… true_marker=… phrase_hit=… fit_residue_ids=[…]
├── 8080/81/82: pid/ppid/unit (untouched)
├── R1 decision: A|B|C|D + reviewer handle
├── writes: none | recover cmd + backup path + verify.sh result
├── files: STATUS / wiki / Mnemosyne updated? paths
└── not done: LARGE=… MID accepted or listed
```

No token-savings claims. No “phases 1–3 complete” copypasta unless R0 still shows it.

## First command

Read-only classify. Do not write. Start at Phase R0.
