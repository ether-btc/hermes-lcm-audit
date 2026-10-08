#!/usr/bin/env python3
"""Phase 3 dry-run probe: exercise the deployed Phase 2.5 guarded summarizer.

Read-only against the live DB. Samples every capacity bucket (fit / boundary25 /
mid / large), loads source messages via lcm_recover.py helpers, and calls the
fork's summarize_with_escalation exactly the way engine.py does — including
model=<LCM_SUMMARY_MODEL> routing so the LLM leg hits the local llama-server
instead of dead OpenRouter.

Classifies each outcome:
  llm             real model summary of full (fitting) input
  llm_lossy_input real model summary of head/tail-truncated input (marker present)
  fallback_l3     escalation chain exhausted -> deterministic truncation string
  error           exception raised

Usage:
  HERMES_HOME=~/.hermes \
  LCM_SUMMARY_MODEL='custom:llama-cpp/Qwen2.5-0.5B-Instruct-Q4_K_M' \
  venv-python scripts/phase3_probe.py [--per-bucket 3] [--out evidence/phase3-probe.json]
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import types
import importlib.util

FORK = os.environ.get("PHASE25_FORK", "/home/hermes-pi/projects/hermes-lcm-phase25")
LIVE_DB = "/home/hermes-pi/.hermes/lcm.db"
SCRIPTS_DIR = "/home/hermes-pi/projects/lcm-hygiene/scripts"

sys.path.insert(0, SCRIPTS_DIR)
import lcm_recover  # noqa: E402  (helpers only; main() is __main__-guarded)


def load_fork():
    pkg = types.ModuleType("hl_p25")
    pkg.__path__ = [FORK]
    sys.modules["hl_p25"] = pkg
    mods = {}
    for name in ("tokens", "config", "model_routing", "escalation"):
        spec = importlib.util.spec_from_file_location(
            f"hl_p25.{name}", f"{FORK}/{name}.py"
        )
        assert spec is not None and spec.loader is not None, f"spec load failed: {name}"
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"hl_p25.{name}"] = mod
        spec.loader.exec_module(mod)
        mods[name] = mod
    return mods


def bucket_of(tokens: int) -> str:
    if tokens <= 3000:
        return "fit"
    if tokens <= 3500:
        return "boundary25"
    if tokens <= 8000:
        return "mid"
    return "large"


def classify(summary: str) -> str:
    if "deterministic truncation" in summary:
        return "fallback_l3"
    if "input head/tail truncation" in summary:
        return "llm_lossy_input"
    return "llm"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-bucket", type=int, default=3)
    ap.add_argument("--out", default="evidence/phase3-probe.json")
    args = ap.parse_args()

    mods = load_fork()
    escalation = mods["escalation"]
    cfg = mods["config"].LCMConfig.from_env()
    model_route = cfg.summary_model
    summarize = escalation.summarize_with_escalation
    count_tokens = escalation.count_tokens

    c = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
    c.execute("PRAGMA busy_timeout=5000")
    rows = c.execute(
        """
        SELECT node_id, session_id, depth, source_ids, source_token_count,
               length(summary) AS old_len
        FROM summary_nodes
        WHERE summary LIKE '%deterministic truncation%'
          AND source_ids <> '[]'
        ORDER BY node_id
        """
    ).fetchall()

    buckets = {}
    for r in rows:
        buckets.setdefault(bucket_of(r[4] or 0), []).append(r)

    print(f"total L3-with-source rows: {len(rows)}")
    for b in ("fit", "boundary25", "mid", "large"):
        print(f"  {b}: {len(buckets.get(b, []))}")

    results = []
    t_all = time.time()
    for b in ("fit", "boundary25", "mid", "large"):
        sample = buckets.get(b, [])[: args.per_bucket]
        for row in sample:
            node_id, session_id, depth, source_ids_json, stc, old_len = row
            rec = {
                "node_id": node_id,
                "bucket": b,
                "source_token_count": stc,
                "old_summary_len": old_len,
            }
            t0 = time.time()
            try:
                msgs = lcm_recover._source_messages(c, json.loads(source_ids_json), session_id)
                text = lcm_recover._serialize_messages(msgs)
                eff_src = stc or count_tokens(text)
                rec["chars"] = len(text)
                rec["trigger_token_overflow"] = count_tokens(text) > 3000
                rec["trigger_chars_overflow"] = len(text) > 12000
                summary, level = summarize(
                    text=text,
                    source_tokens=eff_src,
                    token_budget=min(12000, max(2000, int(eff_src * 0.20))),
                    depth=depth,
                    model=model_route,
                    timeout=90,
                )
                rec["duration_s"] = round(time.time() - t0, 1)
                rec["outcome"] = classify(summary or "")
                rec["summary_len_chars"] = len(summary or "")
                rec["summary_preview"] = (summary or "")[:160].replace("\n", " ")
            except lcm_recover.CrossSessionSourceError:
                rec["outcome"] = "skipped_cross_session"
                rec["duration_s"] = round(time.time() - t0, 1)
            except Exception as e:
                rec["outcome"] = "error"
                rec["error"] = f"{type(e).__name__}: {e}"[:200]
                rec["duration_s"] = round(time.time() - t0, 1)
            results.append(rec)
            print(
                f"[{b}] node={node_id} src~{stc} -> {rec['outcome']} "
                f"({rec['duration_s']}s)"
            )

    c.close()

    by_outcome = {}
    for r in results:
        by_outcome[r["outcome"]] = by_outcome.get(r["outcome"], 0) + 1

    report = {
        "generated_epoch": int(t_all),
        "fork": FORK,
        "model_route": model_route,
        "rows_total": len(rows),
        "buckets": {b: len(buckets.get(b, [])) for b in buckets},
        "sampled": len(results),
        "outcomes": by_outcome,
        "results": results,
        "wall_seconds": round(time.time() - t_all, 1),
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    print("\nOUTCOMES:", json.dumps(by_outcome))
    print(f"report -> {args.out}")


if __name__ == "__main__":
    main()
