# Compression "30s timeout" Warning — 3-Model Review

**Date:** 2026-08-25 (CEST, UTC+02:00)
**Author:** Hermes Agent
**Status:** Assessment complete. No config changes applied. Awaiting owner decision.
**Severity of underlying problem:** Higher than the surface warning suggests. See *Silent quality loss* below.

---

## TL;DR

A "⚠️ Context compression timed out after 30.0s" warning has been firing intermittently during long sessions. Three independent reviews (Codex pass 1, Codex pass 2, GLM-5.2 as R3 tiebreaker) converged on a single recommended fix: **Option C**, which is three config-only edits. The third model caught two structural facts both Codex passes missed: the LCM summary route is pinned via systemd env file (not config.yaml), and the 30s hygiene fence is a total-time budget on the LCM path because LCM never ticks the progress fence.

A more important finding than the warning itself: **LCM compression has been silently producing lossy deterministic truncation instead of real summaries** for a while. The 30s warning is actually the *honest* signal in the system.

---

## How the review was conducted

Three independent passes, each in its own fresh context, each with read-only access to the codebase:

| Round | Model | Method | Output |
|---|---|---|---|
| Pass 1 | Codex | 3-iteration conversation, ~90s | `/tmp/codex-review-v2-pass1.log` |
| Pass 2 | Codex (independent of Pass 1) | 3-iteration conversation, ~210s | `/tmp/codex-review-v2-pass2.log` |
| R3 (tiebreaker) | GLM-5.2 via ZAI | Delegated subagent, 702s, 28 tool calls | `/home/hermes-pi/.hermes/cache/delegation/subagent-summary-0-20260825_201525_220289.txt` (12,733 bytes) |

R3 was instructed to read both Codex transcripts and act as a critical referee. It also curled `http://127.0.0.1:8080/v1/models` to confirm `n_ctx=4096`, traced the actual incident timeline in `~/.hermes/logs/gateway.log`, and read the LCM plugin source end-to-end.

---

## What both Codex passes got wrong

### Miss 1: The env file overrides config.yaml

`~/.config/hermes-gateway.env:28` sets:

```
LCM_SUMMARY_MODEL=custom:llama-cpp/Qwen2.5-0.5B-Instruct-Q4_K_M
```

LCM reads this at engine config time and uses it as the authoritative summary route, regardless of what `~/.hermes/config.yaml:111` says (`custom:llama-cpp/Qwen3-0.6B-Instruct-Q8_0`). Both Codex passes analyzed config.yaml as if it were the live configuration. It is not — at least not for the LCM summary path. Verified in `plugins/hermes-lcm/config.py:266-298` and the `_EnvFieldSpec` registration of `summary_model`.

Consequence: Pass 1's "align to Qwen2.5" recommendation is already live. It would have been a no-op. Pass 2 correctly refused this fix but for the wrong reason.

### Miss 2: The hygiene timeout is a total-time budget on the LCM path

The hygiene warning fires when `commit_fence.seconds_since_progress() > hygiene_timeout_seconds`. The fence is ticked only by the **native Hermes compressor** at `agent/conversation_compression.py:3019-3022`. The LCM plugin has **zero references** to `commit_fence`, `touch_progress`, or `aux_progress_hook` (R3 grep confirmed across `plugins/hermes-lcm/`).

When LCM does a summary via `_call_llm_for_summary` (`plugins/hermes-lcm/escalation.py:229`), it calls `agent.auxiliary_client.call_llm` directly without bridging progress back to the gateway. So even when LCM is actively working on a slow call, the fence sees silence. The entire 30-vs-90-vs-120 debate happened on false semantics — the timeout is not measuring inactivity, it's measuring wall time.

---

## Silent quality loss (this is the worse finding)

Traced from the incident timeline at 18:39–18:42 UTC on 2026-08-25 (`~/.hermes/logs/gateway.log`):

| Time | Event |
|---|---|
| 18:39:53,168 | Hygiene fired. Fence expired at +30s. |
| 18:40:28,589 | User-facing warning displayed. |
| 18:41:28,760 | LCM summary call #1 timed out (`LCM_SUMMARY_TIMEOUT_MS=45000`). |
| 18:42:04,213 | LCM summary call #2 timed out. |
| 18:42:44,242 | Pass "succeeded": `LCM leaf compaction finished in 165987.8ms`, `compaction #1: 50→40, 69760→41065 tokens`. |

The pass "succeeded" because after four failures the circuit breaker opened (`plugins/hermes-lcm/config.py:585-587`, 300s cooldown) and LCM fell back to L3 deterministic truncation via `escalation.py:604-606` in ~1.9 seconds. Log line at 18:14:23 UTC confirms the same pattern: `LCM leaf compaction finished in 1886.7ms` after the circuit opened.

This means recent LCM summaries in this environment have been **deterministic truncations, not real summaries**. The summary output still has the right shape (correct token counts, correct compression-ratio log line) but the content is "oldest messages dropped" rather than "oldest messages condensed." If any downstream system relies on those summaries — recall, memory consolidation, Mnemosyne sleep-time reflection — the recent ones are corrupted in a way the logs do not flag.

Hygiene also recorded a 300s failure cooldown against a session whose compression actually completed, and the user-facing text said "Run /compress to retry" (`gateway/run.py:19893-19901`). The warning is not just noisy; it is wrong about the outcome.

---

## Operational constraints R3 surfaced

**Hot-reloadable vs restart-required knobs:**

| Setting | File | Restart needed? |
|---|---|---|
| `compression.hygiene_*` | `~/.hermes/config.yaml` | No — hot-reloads per hygiene run (`gateway/run.py:19463` → `_load_gateway_config` at `gateway/run.py:3652`) |
| `LCM_*` env keys | `~/.config/hermes-gateway.env` | Yes — gateway service restart (`systemctl --user restart hermes-gateway`). Not a llama-server restart. |

**Config.yaml coverage of LCM fields is narrower than it looks.** `_SUPPORTED_LCM_CONFIG_YAML_KEYS = {"context_threshold"}` (`plugins/hermes-lcm/config.py:202`). A `lcm.leaf_chunk_tokens` key written to config.yaml would be silently ignored. Only the env var or the LCM-specific block works.

**The 64K guard interaction.** `MINIMUM_CONTEXT_LENGTH = 64_000` at `agent/model_metadata.py:413`, checked at `agent/conversation_compression.py:1733-1743`, throws `ValueError` if a model reports fewer context tokens. The Frankenstein route in config.yaml:111 (Qwen3-0.6B name under the `llama-cpp` provider whose `base_url=:8080` runs Qwen2.5-0.5B) would trip this if the env override ever drops. That is why R3 recommended fixing the config.yaml model name even though it is not currently the live route.

---

## Option C — final recommendation from R3

Three config edits, all reversible, no llama-server restarts:

### Edit 1: `~/.hermes/config.yaml` — bump hygiene timeout

```yaml
compression:
  hygiene_timeout_seconds: 120
```

Hot-reloads. Single biggest win for the warning rate. Precedent: `agent/conversation_compression.py:719` already defines `DEFAULT_CONTEXT_TIMEOUT_SECONDS = 120.0`. Current default 30s is structurally inconsistent with `LCM_SUMMARY_TIMEOUT_MS=45000` (env:29) — a single healthy-but-slow call is guaranteed to trip hygiene before its own timeout fires.

### Edit 2: `~/.config/hermes-gateway.env` — shrink leaf chunks

Add (or modify):

```
LCM_LEAF_CHUNK_TOKENS=***
```

Then `systemctl --user restart hermes-gateway`. Not a llama-server restart.

The 234 `exceeds the available context size` 400s in the gateway log are prompt-only overflows against `n_ctx=4096` (verified live on `:8080`; `wrapper.sh:23` sets `-c 4096`). With 2000-token leaves the prompts fit. The rescue path's shrink floor at `plugins/hermes-lcm/engine.py:1559` becomes usable again. Trade-off: roughly 3–4× more LLM calls, so the spend guard (`LCM_SUMMARY_SPEND_MAX_CALLS=24` over 600s, env:32-33) may exhaust mid-pass on huge backlogs — accept partial L3 fallback as graceful degradation.

### Edit 3: `~/.hermes/config.yaml:111` — fix the Frankenstein route

Change `auxiliary.compression.model` from:

```yaml
custom:llama-cpp/Qwen3-0.6B-Instruct-Q8_0
```

to match what the env file already pins:

```yaml
custom:llama-cpp/Qwen2.5-0.5B-Instruct-Q4_K_M
```

Hot-reloads. Bookkeeping only today (env wins at runtime), but prevents the 64K guard from rejecting this route if the env override ever drops.

---

## What R3 explicitly says NOT to touch

- The three mlocked llama-servers and `wrapper.sh`. The `-c 4096` constraint is the situation, not the bug.
- The top-level model and `auxiliary.free_only: true`. Correctly satisfied by the local custom route.
- `context.engine: lcm`. LCM is the right engine; it is just misconfigured downstream.
- `compression.enabled: false`. Would defeat hygiene entirely.
- Pass 2's nonexistent ≥64K local model. `free_only` excludes remote, and "no model swaps" was a hard constraint.

---

## Open question for the owner

Recent LCM summaries in this environment are deterministic truncations, not real summaries. Before deciding what subset of Option C to apply, it is worth understanding **what those summaries are used for downstream** — recall, memory consolidation, sleep-time reflection, conversation resumption. If any of those read the corrupted summaries, the fix should be prioritized. If they read raw transcripts directly, Option C is a quality-of-life improvement rather than a correctness fix.

---

## Artifacts

| Path | Content |
|---|---|
| `/tmp/codex-review-v2-pass1.log` | Codex pass 1 transcript |
| `/tmp/codex-review-v2-pass2.log` | Codex pass 2 transcript |
| `/tmp/solar-review-prompt.md` | R3 prompt brief |
| `/home/hermes-pi/.hermes/cache/delegation/subagent-summary-0-20260825_201525_220289.txt` | R3 final summary, 12,733 bytes |
| `/home/hermes-pi/.hermes/cache/delegation/live/deleg_cea618db/task-0.log` | R3 full tool/assistant trace, 29,727 bytes |
| `~/.hermes/logs/gateway.log` (lines ~7790-7830) | Incident timeline at 18:39-18:42 |
| `~/.hermes/config.yaml:111` | Current `auxiliary.compression.model` (Frankenstein route) |
| `~/.hermes/config.yaml:309-315` | `custom_providers.llama-cpp` definition |
| `~/.config/hermes-gateway.env:27-34` | Live LCM env overrides |
| `agent/conversation_compression.py:719` | `DEFAULT_CONTEXT_TIMEOUT_SECONDS = 120.0` |
| `agent/conversation_compression.py:1733-1743` | 64K guard rejecting undersized contexts |
| `agent/conversation_compression.py:2996-3022` | Where `touch_progress` is wired (native only) |
| `agent/model_metadata.py:413` | `MINIMUM_CONTEXT_LENGTH = 64_000` |
| `plugins/hermes-lcm/__init__.py:512` | LCM entry into Hermes compressor |
| `plugins/hermes-lcm/config.py:202` | `_SUPPORTED_LCM_CONFIG_YAML_KEYS = {"context_threshold"}` |
| `plugins/hermes-lcm/config.py:585-587` | Circuit breaker open: 4 failures, 300s cooldown |
| `plugins/hermes-lcm/engine.py:1559` | Rescue-shrink floor at `leaf_chunk_tokens` |
| `plugins/hermes-lcm/escalation.py:229-256` | `_call_llm_for_summary` (no progress hook) |
| `plugins/hermes-lcm/escalation.py:387-392` | Spend guard |
| `plugins/hermes-lcm/escalation.py:604-606` | L3 deterministic truncation fallback |
| `gateway/run.py:19463` | Hot-reload of hygiene config |
| `gateway/run.py:19893-19901` | "Run /compress to retry" user-facing message |

## Mnemosyne references

- `049b7d754dc67737` — initial R3 root-cause summary (superseded by full report)
- `03a39d48d275cade` — corrected R3 full findings (load-bearing for this audit)
- `f62133f498b4d3a4` — owner preference about Codex append work during concurrent sessions

---

## Handoff

Owner decision pending. Recommended execution order if greenlit:

1. **Edit 1 alone** as a no-restart first step. Confirm the warning rate drops within 2-3 long sessions before touching anything else.
2. **Edit 3** in the same `config.yaml` edit pass. Zero risk.
3. **Edit 2** at the next scheduled gateway maintenance window. Service restart only.

Each step is independently reversible. Each step is verified by the next occurrence of a long-session hygiene run.
