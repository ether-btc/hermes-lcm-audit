# LCM Truncation — Decision Record 2026-08-26 (accept MID/LARGE, zero-diff)

Date: 2026-08-26 19:45 CEST
Phase25 HEAD: 915bec0 (symlink ~/.hermes/plugins/hermes-lcm → phase25, 23:09 deploy pre-flip 23:19)
Reviews: deleg_33e1e77b Codex SHIP-AS-PLANNED + GLM SHIP-AS-IS (both read-only)

## VERIFIED R0 (read-only, stricter marker `[...deterministic truncation —`)
- total summary_nodes 1382; true L3 295 (FIT 75 / MID 7 / LARGE 213) all-time
- post-flip 80/161 (FIT 63 / MID 3 / LARGE 14) @ 2026-08-25 23:19 CEST flip
- input-truncation marker = 0 firings (guard never triggered post-flip)
- FIT L3 sample src 561–2476 (under 3000 budget) → not input overflow
- Host: 389Mi free / 6.4G used / 5.7G swap; PIDs 1113/1114 swapped-out (2.7/4.4 MB RSS), :8082 mlock risk

## Decisions
- **MID extend: REJECT.** Saves 3/80 post-flip nodes (~1.9%); impossible on 4096-ctx model (MID 4334/6248/6283 exceed ctx); RAM-gated by swap thrashing + hermes-llama@8081 failed.
- **LARGE chunk-and-stitch: REJECT.** 14 recoverable nodes; lcm_expand recovers source; cost >> gain.
- **Accept L3 truncation for MID/LARGE: ACCEPT (ponytail zero-diff).** Deterministic fallback is functioning convergence; all post-flip L3 are recoverable (source_ids nonempty) + bounded lcm_expand_query pagination exists.
- **Root cause callout (GLM falsification):** 63 post-flip FIT L3 are circuit-breaker driven (`LCM summary route skipped by open circuit: Qwen2.5-0.5B` in gateway logs), not guard predicate. Any future spend should target circuit سببب not guard threshold.
- **Model retire (Phi-4-mini → Qwen3-4B): DEFERRED** per plan DRAFT + host swap pressure; Qwen3-4B is 2.56G vs 2.38G (disk not RAM win).

## Hypothesis disposition (6 hypotheses from inventory)
H1 never-fires = VERIFIED (0 input trunc); H2 write-path bug = falsified (marker distinct, guard correct); H3 FIT output-limited = VERIFIED (circuit); H4 cross-session = partial (LARGE includes historical 08-09 burst 202 nodes); H5 RAM gate = VERIFIED; H6 timeout race = plausible (90 vs 120 but not today's limiter — circuit dominates)

## Replay sentence
When MID/LARGE truncation occurs on n_ctx=4096, accept deterministic L3 (recoverable via lcm_expand) because the pre-flight input guard is correctly sized at 3000/4096 and never fired post-flip, while FIT L3 is circuit-breaker driven — so enlarging the guard or swapping models saves ≤3 nodes at host-destabilizing cost.

## Blast radius
Zero-diff path = none. Optional fallback clamp (tools.py:5524, expansion_context 4096 for local routes) affects only lcm_expand_query and is not applied.

## Next step (if ever)
Investigate Qwen2.5-0.5B circuit openings (timeout vs error) before any guard touch; keep symlink flip as only reversible lever.
