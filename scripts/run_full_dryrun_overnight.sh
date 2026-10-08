#!/usr/bin/env bash
# Phase 3 FULL dry-run scheduler (zero-write: --dry-run --live).
# Waits for an off-peak window AND for any running lcm_recover.py to finish,
# then executes the full widened population (source tokens <= 3500, ~147 nodes).
set -u
cd /home/hermes-pi/projects/lcm-hygiene

TARGET_EPOCH=$(date -d "today 03:30" +%s)
NOW=$(date +%s)
if [ "$NOW" -ge "$TARGET_EPOCH" ]; then
    TARGET_EPOCH=$(date -d "tomorrow 03:30" +%s)
fi
echo "[scheduler] $(date '+%F %T') waiting until $(date -d @$TARGET_EPOCH '+%F %T %Z')"

sleep $((TARGET_EPOCH - $(date +%s)))

# Never overlap with another recovery/probe process on :8080.
while pgrep -f "scripts/(lcm_recover|phase3_probe)\.py" >/dev/null; do
    echo "[scheduler] $(date '+%F %T') another recover/probe still running; waiting 5 min"
    sleep 300
done

echo "[scheduler] $(date '+%F %T') window reached, launching FULL dry-run"
HERMES_HOME=/home/hermes-pi/.hermes \
LCM_SUMMARY_MODEL="custom:llama-cpp/Qwen2.5-0.5B-Instruct-Q4_K_M" \
/home/hermes-pi/.hermes/hermes-agent/venv/bin/python scripts/lcm_recover.py \
    --db "$HOME/.hermes/lcm.db" \
    --dry-run --live \
    --plugin-dir /home/hermes-pi/projects/hermes-lcm-phase25 \
    --max-source-tokens 3500 \
    > evidence/phase3-dryrun-full.log 2>&1
EXIT=$?
echo "[scheduler] $(date '+%F %T') FULL dry-run finished exit=$EXIT"
tail -5 evidence/phase3-dryrun-full.log
exit $EXIT
