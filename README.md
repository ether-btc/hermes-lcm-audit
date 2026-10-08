# LCM Silent-Truncation Hygiene

**Codename:** lcm-hygiene
**Owner:** Hermes Agent (per CEO delegation, 2026-08-23 SWE-team-lead standing contract)
**Started:** 2026-08-25 (CEST, UTC+02:00)
**Phase:** M1 ready / M2-M4 pending
**Repo:** `~/projects/lcm-hygiene/` (local-only, no remote)
**Spec anchors:** `~/hermes-vault/audits/compression-30s-warning-3-model-review-2026-08-25.md`, `lcm-silent-truncation-verification-2026-08-25.md`, `lcm-silent-truncation-r1r3-refinement-2026-08-25.md`

## What this is

A project to (a) stop the LCM silent-truncation bleed, (b) recover the 405 recoverable corrupted nodes, (c) characterize the 203 unrecoverable loss, (d) capture the verdict that the GLM R3 subagent ran out of iteration budget before writing. Recovered script + tests live under `scripts/`, evidence under `evidence/`, state snapshots under `evidence/snapshots/`.

## Why this is non-trivial

Three independent reviewers (Codex P1, Codex P2, GLM-5.2 R3) converged on the fix direction but the parent audit's primary recommendation (Edit 1: add `compression.hygiene_timeout_seconds` to YAML) was discovered by R1 refinement to be a **phantom key** — it does not exist in the codebase and any patch built on it would be silently no-op'd by Hermes' config loader. The R1R3 refinement replaced it with the real env knob (`LCM_SUMMARY_TIMEOUT_MS=90000`). 52.4% of summary nodes (608 / 1161) have been silently storing deterministic truncation as "summaries" — the warning surface is honest, the storage is dishonest. Recovery touches external-content FTS5 (must use delete-insert, not UPDATE).

## How it fits

```
[hermes-agent compression] -> [lcm plugin] -> [summarize_with_escalation]
                                                  |- L1 (LLM detail)
                                                  |- L2 (LLM bullets)
                                                  |- L3 (_deterministic_truncate) <-- silently stored as "summary"
                                                  |
                                                  v
                                          [summary_nodes table] --triggers--> [nodes_fts external-content FTS5]

[scripts/lcm_recover.py] --FTS-only-first--> [delete-insert pattern] --opt-in --live--> [LLM re-summarize]
```

## Non-goals (v1)

- Replacing hermes-lcm with another memory engine (assessed separately, see `projects/audits/opencode-mem-audit.md`).
- Resummarizing the 203 unrecoverable nodes (their source_ids are empty — loss is permanent, only inventory is possible).
- Speculative magnitude changes without Codex synthesis.
- Live LLM recovery unless `--live` flag is passed (per Codex's v2 scoped brief).

## Hard constraints

- Never bind 0.0.0.0 (standing user policy).
- LCM recovery must use delete-insert pattern on `nodes_fts`; never `UPDATE` on external-content FTS5 (Codex v1/v2 proven).
- LCM_* env vars are cold-knobs — gateway restart required, not llama-server (per Mnemosyne 2026-08-25 R3).
- `compression.hygiene_timeout_seconds` is NOT a real key — never write a config.yaml edit built on it.
- Status numeric claims must be backed by literal runnable commands (project-planning evidence rule, validated 2026-08-23 on PROMPRO).

## Project layout

```
~/projects/lcm-hygiene/
├── README.md                  this file
├── PRAXIS.md                  problem, goal, scope, gates, done
├── ROADMAP.md                 riskiest-first milestones + task table
├── DECISIONS.md               append-only ADR log
├── STATUS.md                  live state, verified facts, handoff
├── EXECUTION-PROMPT.md        self-contained resume prompt for next session
├── scripts/
│   ├── lcm_recover.py         Codex v2 recovery script (delete-insert FTS pattern, --live opt-in)
│   └── verify.sh              M1/M2/M3/M4 gate checks
└── evidence/
    ├── deleg_7fbffac1-task-0.log       GLM R3 transcript (transcript complete, synthesis truncated)
    ├── codex-script-v2-stdout.txt     Codex v2 build-task transcript
    ├── compression-30s-warning-3-model-review-2026-08-25.md   parent audit (Codex P1 + Codex P2 + GLM R3)
    ├── lcm-silent-truncation-verification-2026-08-25.md       R1 independent verification
    ├── lcm-silent-truncation-r1r3-refinement-2026-08-25.md    R3 plan refinement (Edit 1 replacement)
    └── snapshots/                       pre/post state snapshots
```

## Tools I'll be using

| Tool | When it fires |
|------|--------------|
| `codex exec` | Codex synthesis on question (1) — magnitude for LCM_SUMMARY_TIMEOUT_MS (read-only, fed GLM transcript). Default per user pref: gpt-5.6-sol on ChatGPT Plus OAuth, no override route. |
| `delegate_task` (glm-5.3 via ZAI) | Second independent vote if Codex output is incoherent (per 2026-08-24 operating model: paid ZAI slot for Hermes delegation, not for reviews of Hermes). |
| `ocr` | Static scan of recovery script before commit (already validated on opencode-mem audit 2026-08-25). |
| `repomix` | Pack the hermes-lcm source slice for Codex's read-only context if it needs re-orientation. |
| `aider` | NOT used in this project (Codex is the technical lead per standing contract; aider would muddy the chain of custody). |
| `rtk` | Filtered reads of hermes-lcm source where grep would over-fire. |
| `lcm_grep` / `mnemosyne_recall` | Cross-session recall (e.g., for Mnemosyne prior LCM decisions). |
| `scripts/verify.sh` | Run on every state-snapshot moment — before reporting M1, before reporting M3, before declaring project ready. |

## Quick-start for "continue later" sessions

- "What state is lcm-hygiene in?" → read `STATUS.md` from `## Current state` down.
- "Resume M1 execution" → follow `EXECUTION-PROMPT.md` from `## Mission`.
- "Re-run M1 verification" → `bash ~/projects/lcm-hygiene/scripts/verify.sh`.
- "Why did Edit 1 change?" → `DECISIONS.md` ADR-2026-08-25-01.
- "What did GLM actually conclude?" → `evidence/deleg_7fbffac1-task-0.log` line 76 truncated; for full conclusion see `EXECUTION-PROMPT.md` §Codex-synthesis scope.

## Risk gates

- **M1 → M2:** `verify.sh` exits 0 (5-step live verification matches pre-restart snapshot; no new L3 nodes during restart).
- **M2 → M3:** 203 unrecoverable nodes have a dated inventory file under `evidence/snapshots/`.
- **M3 → M4:** `verify.sh` L3-with-source_ids count near zero; UPDATE-only idempotency proven.
- **M4 → done:** Mnemosyne read-path verdict filed; full project scaffold exists; verify.sh exits 0; next session resume works cold.

## Open items blocking Phase 1 start

- Codex synthesis on magnitude for LCM_SUMMARY_TIMEOUT_MS (Task 1.2, the load-bearing question — see EXECUTION-PROMPT).
- Whether 90000ms (R3 recommendation) or 60000ms (initial GLM framing) or another number is correct after Codex's read of the transcript.

## Sister-repo references

- `~/projects/hermes-lcm/` — source tree; we read but never edit.
- `~/projects/audits/opencode-mem-audit.md` — adjacent audit on potential LCM replacement (NO — sidecar only).
- `~/hermes-vault/audits/` — parent + refinement + verification documents.

## License

Internal project, no external license. All references to upstream code (Codex v2 script, hermes-lcm source) are read-only.