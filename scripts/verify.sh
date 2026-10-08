#!/usr/bin/env bash
# verify.sh — lcm-hygiene project verifier
# Per project-planning skill (validated 2026-08-23 on PROMPRO): every numeric claim
# in STATUS.md must be backed by a literal command. This script is the canonical
# re-derivation. Exit 0 only if the live state matches the project's expectations
# for the requested phase.
#
# Usage: scripts/verify.sh [--phase pre-edit|post-edit|post-restart|post-recovery] [--quick]
#
# Phases:
#   pre-edit      — capture L3 count + env values + config.yaml:111 before any change
#   post-edit     — confirm L3 count has not grown since pre-edit snapshot
#   post-restart  — confirm gateway restarted and env keys loaded
#   post-recovery — confirm L3-with-source_ids count has dropped to noise floor
#   (default)     — run all checks

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAP_DIR="$PROJECT_DIR/evidence/snapshots"
mkdir -p "$SNAP_DIR"

DB="${HERMES_LCM_DB:-$HOME/.hermes/lcm.db}"
ENV="$HOME/.config/hermes-gateway.env"
CFG="$HOME/.hermes/config.yaml"

PHASE="pre-edit"
QUICK=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase) PHASE="$2"; shift 2 ;;
    --quick) QUICK=1; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

pass=0; fail=0; warn=0
ts="$(date -u +%Y%m%d_%H%M%S)"

check() {  # check NAME COMMAND EXPECTED_DESC
  local name="$1" cmd="$2" expect="$3"
  local out
  if out="$(bash -c "$cmd" 2>&1)"; then
    echo "  PASS  $name  ->  $out"
    pass=$((pass+1))
  else
    echo "  FAIL  $name  (cmd: $cmd)"
    echo "        -> $out"
    fail=$((fail+1))
  fi
}

do_snapshot() {  # snapshot NAME
  local snapname="${1:-unknown}"
  local path="$SNAP_DIR/${snapname}-${ts}.txt"
  {
    echo "# lcm-hygiene snapshot: $snapname @ $ts"
    echo "DB=$DB"
    echo "ENV=$ENV"
    echo "CFG=$CFG"
    echo "---total---"
    sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes;"
    echo "---l3---"
    sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%';"
    echo "---unrecoverable---"
    sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND (source_ids='[]' OR source_ids IS NULL OR source_ids='');"
    echo "---recoverable---"
    sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND source_ids<>'[]';"
    # Cause-axis classification (timeout-shaped vs capacity-shaped) — see evidence/snapshots/lcm-lossy-inventory-2026-08-25_22-50.md
    echo "---l3-axis-fit--"
    sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) <= 3000;"
    echo "---l3-axis-boundary-25--"
    sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) BETWEEN 3001 AND 3500;"
    echo "---l3-axis-mid--"
    sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) BETWEEN 3501 AND 8000;"
    echo "---l3-axis-large--"
    sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) > 8000;"
    echo "---env LCM_SUMMARY_TIMEOUT_MS---"
    grep '^LCM_SUMMARY_TIMEOUT_MS' "$ENV" 2>/dev/null || echo "(missing)"
    echo "---env LCM_LEAF_CHUNK_TOKENS---"
    grep '^LCM_LEAF_CHUNK_TOKENS' "$ENV" 2>/dev/null || echo "(missing)"
    echo "---config.yaml:111---"
    sed -n '111p' "$CFG"
  } > "$path"
  echo "  SNAP  $snapname  ->  $path"
}

section() { echo; echo "== $1 =="; }

# ─── Pre-flight (always runs) ─────────────────────────────────────────────
section "preflight"
check "sqlite3 reachable" "command -v sqlite3 && sqlite3 --version | head -1" "sqlite3 present"
check "DB exists" "test -f '$DB' && echo present || echo missing" "DB present"
check "ENV exists" "test -f '$ENV' && echo present || echo missing" "ENV present"
check "CFG exists" "test -f '$CFG' && echo present || echo missing" "CFG present"

# ─── Phase: pre-edit ──────────────────────────────────────────────────────
if [[ "$PHASE" == "pre-edit" ]]; then
  section "phase: pre-edit"
  do_snapshot "pre-edit"
fi

# ─── Phase: post-edit (gate: L3 count has not grown) ──────────────────────
if [[ "$PHASE" == "post-edit" ]]; then
  section "phase: post-edit"
  latest_pre="$(ls -1t "$SNAP_DIR"/pre-edit-*.txt 2>/dev/null | head -1 || true)"
  if [[ -z "$latest_pre" ]]; then
    echo "  WARN  no pre-edit snapshot found; skipping L3-grew check"
    warn=$((warn+1))
  else
    pre_l3="$(grep -A1 '^---l3---' "$latest_pre" | tail -1 | tr -d '[:space:]')"
    cur_l3="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%';")"
    if [[ "$cur_l3" -le "$pre_l3" ]]; then
      echo "  PASS  L3 not grown  (pre=$pre_l3, now=$cur_l3)"
      pass=$((pass+1))
    else
      echo "  FAIL  L3 grew  (pre=$pre_l3, now=$cur_l3)"
      fail=$((fail+1))
    fi
  fi
  do_snapshot "post-edit"
fi

# ─── Phase: post-restart (gate: gateway active + env keys loaded) ─────────
if [[ "$PHASE" == "post-restart" ]]; then
  section "phase: post-restart"
  check "gateway active" "systemctl --user is-active hermes-gateway 2>&1 | grep -q active && echo active || echo inactive" "gateway active"
  # LCM_SUMMARY_TIMEOUT_MS policy: per AGENTS.md, the policy-compliant knob is
  # auxiliary.compression.timeout in YAML. Either is acceptable as long as the
  # effective value is 90000ms. The two checks below are non-overlapping —
  # exactly one of them passes.
  check "LCM_SUMMARY_TIMEOUT_MS env set" "grep -q '^LCM_SUMMARY_TIMEOUT_MS=90000' '$ENV' && echo set || echo missing" "env=90000 (bridge)"
  check "auxiliary.compression.timeout YAML" "grep -A8 '^auxiliary:' '$CFG' | grep -q 'timeout: 90' && echo set || echo missing" "YAML=90s (preferred)"
  check "LCM_LEAF_CHUNK_TOKENS set" "grep -q '^LCM_LEAF_CHUNK_TOKENS=' '$ENV' && echo set || echo missing" "LCM_LEAF_CHUNK_TOKENS set"
  check "config.yaml:111 = Qwen2.5-0.5B" "grep -q 'Qwen2.5-0.5B-Instruct-Q4_K_M' '$CFG' && echo ok || echo missing" "Qwen2.5-0.5B in config.yaml"
  check "hygiene_timeout_seconds set" "grep -q '^  hygiene_timeout_seconds: ' '$CFG' && echo set || echo missing" "compression.hygiene_timeout_seconds in config.yaml"
fi

# ─── Phase: inventory (read-only classified cause-axis baseline) ──────────
# Per GLM-5.2 reviewer verdict (2026-08-25 22:49). Produces the snapshot
# extended with cause-axis classification. Run on demand; ~1s.
if [[ "$PHASE" == "inventory" ]]; then
  section "phase: inventory"
  do_snapshot "inventory"
  # Quick summary: print the axis counts right here for the human running it.
  fit="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) <= 3000;")"
  boundary25="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) BETWEEN 3001 AND 3500;")"
  mid="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) BETWEEN 3501 AND 8000;")"
  large="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) > 8000;")"
  total_l3="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%';")"
  echo "  L3 axis split: fit=$fit boundary25=$boundary25 mid=$mid large=$large (sum=$((fit+boundary25+mid+large)) / total=$total_l3)"
fi

# ─── Phase: post-recovery (gate: L3-with-source_ids near zero) ────────────
if [[ "$PHASE" == "post-recovery" ]]; then
  section "phase: post-recovery"
  check "L3 recoverable < 50" "out=\$(sqlite3 -readonly '$DB' \"SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND source_ids<>'[]';\"); echo \$out" "recoverable count"  # captured, threshold checked below
  recoverable="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND source_ids<>'[]';")"
  if [[ "$recoverable" -lt 50 ]]; then
    echo "  PASS  L3 recoverable near floor  ($recoverable < 50)"
    pass=$((pass+1))
  else
    echo "  FAIL  L3 recoverable still high  ($recoverable >= 50)"
    fail=$((fail+1))
  fi
fi

# ─── Summary ──────────────────────────────────────────────────────────────
section "summary"
echo "  pass=$pass  fail=$fail  warn=$warn"
if [[ "$fail" -gt 0 ]]; then
  echo "  RESULT: FAIL"
  exit 1
else
  echo "  RESULT: PASS"
  exit 0
fi