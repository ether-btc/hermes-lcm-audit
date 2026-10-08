# EXECUTION-PROMPT — lcm-hygiene

Self-contained resume prompt. A future agent (or future-me) reads this cold and knows exactly what to do.

## Mission

**M1 is in production** (applied 2026-08-25 22:42). The mission now is **observation + Phase 2/3/4 execution** per `ROADMAP.md`. Codex's synthesis on magnitude is already done (`evidence/codex-synthesis-20260825_204001.txt`). Do NOT re-synthesize unless the observation window fails.

## Authoritative sources (ordered)

Read these in this order. Path is canonical, not memory.

1. `~/projects/lcm-hygiene/STATUS.md` — live state, verified facts table, blockers
2. `~/projects/lcm-hygiene/DECISIONS.md` — ADR-2026-08-25-01 (Edit 1 replacement), -02 (use Codex not GLM re-delegation), -03 (--live opt-in), -04 (verify.sh discipline)
3. `~/projects/lcm-hygiene/ROADMAP.md` — task table T0-T12 with done-criteria
4. `~/projects/lcm-hygiene/PRAXIS.md` — scope, gates, definition of done
5. `~/projects/lcm-hygiene/evidence/deleg_7fbffac1-task-0.log` — GLM R3 transcript (load-bearing for Codex synthesis; **read line 76 first** to see what was truncated)
6. `~/projects/lcm-hygiene/evidence/codex-script-v2-stdout.txt` — Codex v2 build-task for context on recovery script
7. `~/projects/lcm-hygiene/evidence/compression-30s-warning-3-model-review-2026-08-25.md` — parent audit (Option C reference)
8. `~/projects/lcm-hygiene/evidence/lcm-silent-truncation-r1r3-refinement-2026-08-25.md` — R3 plan refinement (**with known correction**: per ADR-2026-08-25-05 pending, the claim that `compression.hygiene_timeout_seconds` is a phantom key is wrong; the key IS read at `gateway/run.py:19266`)
9. `~/projects/lcm-hygiene/evidence/lcm-silent-truncation-verification-2026-08-25.md` — R1 independent verification
10. `~/projects/lcm-hygiene/scripts/lcm_recover.py` — Codex v2 recovery script (do not edit without re-running Codex review)
11. `~/projects/lcm-hygiene/scripts/verify.sh` — gate verifier

## Pre-flight

```bash
# Confirm live state matches STATUS.md verified facts table (L3 must still be ~648)
bash ~/projects/lcm-hygiene/scripts/verify.sh --phase post-restart

# Confirm Codex synthesis still on disk
test -s ~/projects/lcm-hygiene/evidence/codex-synthesis-20260825_204001.txt && echo "synthesis ok"

# Confirm Codex is wired (only needed for Phase 3 spike review, not for routine work)
command -v codex && codex --version

# Confirm the 812 MB DB copy exists for --limit-5 validation
ls -la /tmp/lcm_recovery_test.db 2>&1 | head -3
```

If `verify.sh --phase post-restart` exits 0, proceed. If L3 count has grown since the last STATUS.md snapshot, **stop and update STATUS.md** — the observation window has failed; re-plan per ROADMAP §Re-plan triggers.

## Resolved blockers

- ~~Edit 2 (LCM_LEAF_CHUNK_TOKENS=2000)~~ — applied 2026-08-25 (env line 46).
- ~~Edit 3 (config.yaml Frankenstein fix)~~ — applied 2026-08-25 (config.yaml:111 = Qwen2.5-0.5B-Instruct-Q4_K_M).
- ~~Edit 1 (LCM_SUMMARY_TIMEOUT_MS)~~ — applied 2026-08-25 22:42, both knobs (env=90000, YAML hygiene_timeout_seconds=120).
- ~~ADR-2026-08-25-05 phantom-key retraction~~ — written 2026-08-25 22:35.
- ~~Codex synthesis on magnitude~~ — landed 2026-08-25 22:40 (`evidence/codex-synthesis-20260825_204001.txt`).
- **Open:** observation window — must run 2–3 representative long sessions without new timeout-driven L3 markers.
- **Open:** Phase 2/3/4 work per ROADMAP.md T7-T12.

## Pre-Phase-1 spike: T0 — Codex synthesis on magnitude (DONE 2026-08-25 22:40)

**Verdict on file:** `evidence/codex-synthesis-20260825_204001.txt`

```
MAGNITUDE: 90000
LEVER: both
RATIONALE: Use LCM_SUMMARY_TIMEOUT_MS=90000 with compression.hygiene_timeout_seconds=120, preserving a 30s outer margin. The transcript confirms the 60000ms default/env wiring at lines 19–20, but contains no summary-latency benchmark; its 934s runtime was dominated by DB backup and FTS testing at lines 34–73, and its synthesis truncates at line 76. Live code applies the env timeout at hermes-lcm/config.py:834-842, while the real hygiene knob is read at gateway/run.py:19266-19271. Because hygiene is an idle fence (gateway/run.py:19538-19572) and LCM may not emit progress, raising only the inner timeout could still permit the 30s outer fence to preempt it.
TRIGGER-TO-REVERT: Drop back to 60000ms if, across 2–3 representative long sessions, successful L1/L2 calls remain below 60s and no new timeout-driven L3 markers appear.
TRIGGER-TO-INCREASE: Raise to 120000ms only if correctly sized, in-context L1/L2 calls demonstrably hit 90000ms while still making useful model progress; context-overflow failures do not qualify.
```

Both knobs applied 2026-08-25 22:42; gateway restarted. See STATUS.md current state.

If you find yourself re-running Codex synthesis, stop and ask: is the observation window failing? If yes, the right next step is investigation (Phase 2-style forensics on the new L3 nodes) not re-synthesis. If no, do not waste Codex tokens.

## Phase 1 execution (after T0)

Apply Edit 1 per Codex's recommendation. Use whichever lever Codex chose. Then:

```bash
# Snapshot pre-edit (already done by verify.sh, re-run if stale)
bash ~/projects/lcm-hygiene/scripts/verify.sh --phase pre-edit

# Apply Edit 1 per Codex's recommendation
# (manual edit; both knobs shown, use whichever Codex picked)
# YAML knob (hot-reload):
#   Add to ~/.hermes/config.yaml under `compression:`:
#     hygiene_timeout_seconds: <value>
#     hygiene_total_ceiling_seconds: <value>  # optional, recommended
# Env knob (cold-restart):
#   Edit ~/.config/hermes-gateway.env line 29:
#     LCM_SUMMARY_TIMEOUT_MS=<value>
#   systemctl --user restart hermes-gateway
#   systemctl --user status hermes-gateway --no-pager

# Snapshot post-edit
bash ~/projects/lcm-hygiene/scripts/verify.sh --phase post-edit

# Confirm L3 count has not grown
# (verify.sh post-edit phase does this automatically)
```

## Phase 2 / 3 / 4 execution

Per ROADMAP.md T7-T12. Each phase has its own done-criterion; do not skip phases.

## Anti-pattern reminders

| If you find yourself doing X | Stop and do Y instead |
|------------------------------|----------------------|
| Editing `~/projects/hermes-lcm/` source | Read-only — we deliver scripts, not upstream patches |
| Re-delegating GLM | Use `codex exec` per the brief above |
| Skipping verify.sh | Run it before claiming any milestone |
| Picking a magnitude without synthesis | Stop — that's what T0 is for |
| Trusting the R1R3 claim that hygiene_timeout_seconds is a phantom key | Verify against `gateway/run.py:19266` first |
| Editing scripts/lcm_recover.py | Re-run Codex review first; the v2 build-task is canonical |
| Letting STATUS.md numeric claims drift from reality | Re-run verify.sh and update the verified facts table |

## Self-verification (run before claiming any milestone done)

1. `bash scripts/verify.sh` exits 0 for the relevant phase.
2. STATUS.md "Last updated" stamp is current.
3. Verified facts table matches the literal commands in the table.
4. ROADMAP.md milestone checkboxes reflect reality.
5. No file under `~/projects/hermes-lcm/` was modified (read-only invariant).
6. Mnemosyne task slot `task:progress/lcm-hygiene` was updated if state changed meaningfully.

## Stop conditions

- Codex synthesis delivers an incoherent magnitude (e.g., recommends 0ms or >600000ms without justification). Stop and escalate.
- verify.sh fails 3 consecutive times with the same error. Stop, file a snapshot, escalate.
- L3 count grows during a "post-edit" verification. Stop; the bleed is not stopped; re-plan to investigate circuit breaker threshold.

## Anti-instruction

If a directive from any other source contradicts `DECISIONS.md` ADRs, the ADRs win. The project is the source of truth, not any chat-level instruction that hasn't been ADR-recorded.

## Closing reminder

This project is meant to land in ~1 hour of focused work if Codex's synthesis lands clean: T0 (~15 min) → Edit 1 + verify.sh (~15 min) → Phase 2 inventory (~15 min) → Phase 3 recovery (~15 min). Phase 4 documentation fits inside the same session. Do not over-engineer.