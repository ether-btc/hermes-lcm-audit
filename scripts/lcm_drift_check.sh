#!/usr/bin/env bash
# lcm_drift_check.sh — observation-window drift log with cause classification
#
# Run once per session to record L3 count and report if it has drifted since
# the M1 application (2026-08-25 22:42, baseline = 648).
#
# Per GLM-5.2 reviewer verdict (2026-08-25 22:49, subagent sa-0-9d70a4f7):
# drift log must classify by cause axis (timeout vs capacity) so that
# M1's TRIGGER-TO-REVERT (timeout-driven only) doesn't fire on
# capacity-driven markers (which M1 cannot fix).
#
# Bucket thresholds: ≤3500 = capacity-fit (Qwen2.5-0.5B n_ctx=4096 minus
# output reserve); 3501-8000 = mid-overflow; >8000 = large-overflow.
# Bucket rationale: evidence/snapshots/lcm-lossy-inventory-2026-08-25_22-50.md
#
# Idempotent: appends a single timestamped line per invocation. Never modifies
# the DB, the env, or the YAML.
#
# Usage: bash scripts/lcm_drift_check.sh [baseline_l3_count]
# Default baseline: 648 (M1 application baseline, see STATUS.md §Verified facts).

set -u

DB="${HOME}/.hermes/lcm.db"
BASELINE="${1:-648}"
LOG="/home/hermes-pi/projects/lcm-hygiene/evidence/drift-log.txt"

if [[ ! -r "$DB" ]]; then
    echo "FATAL: cannot read $DB" >&2
    exit 2
fi

# Headline counts
total="$(sqlite3 -readonly "$DB" 'SELECT count(*) FROM summary_nodes;')"
l3="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%';")"
unrecoverable="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND (source_ids='[]' OR source_ids IS NULL OR source_ids='');")"
recoverable="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND source_ids<>'[]';")"

# Cause-axis classification — bucket L3 markers by depth × source_token_count
fit="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) <= 3500;")"
mid="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) BETWEEN 3501 AND 8000;")"
large="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND COALESCE(source_token_count,0) > 8000;")"

# Post-flip cohort (Phase 2.5 guard deployed 2026-08-25 23:19 CEST). The
# observation-window exit criterion counts ONLY these: any marker created on a
# post-flip node means the guard failed to prevent a new lossy L3.
postflip_l3="$(sqlite3 -readonly "$DB" "SELECT count(*) FROM summary_nodes WHERE summary LIKE '%deterministic truncation%' AND created_at >= strftime('%s','2026-08-25T23:19:00 +02:00');")"

delta=$(( l3 - BASELINE ))
status="OK"
if (( delta > 0 )); then
    status="DRIFT"
elif (( delta < 0 )); then
    status="UNKNOWN"
fi

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf "%s\tstatus=%s\ttotal=%s\tl3=%s\tdelta_vs_baseline=%+d\tunrecoverable=%s\trecoverable=%s\taxis=fit=%s,mid=%s,large=%s\tpostflip_l3=%s\n" \
    "$ts" "$status" "$total" "$l3" "$delta" "$unrecoverable" "$recoverable" "$fit" "$mid" "$large" "$postflip_l3" \
    >> "$LOG"

echo "$ts $status l3=$l3 (baseline=$BASELINE, delta=$delta) unrecoverable=$unrecoverable recoverable=$recoverable axis=fit=$fit,mid=$mid,large=$large postflip_l3=$postflip_l3"
echo "appended to $LOG"