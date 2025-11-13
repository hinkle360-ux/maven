#!/bin/bash
# Run the regression harness and log output by date
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$ROOT_DIR/reports/nightly_regression"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/regression_$(date +%Y%m%d).log"
python3 "$ROOT_DIR/tools/regression_harness.py" > "$LOG_FILE" 2>&1
echo "Regression run complete: $LOG_FILE"
# Generate a summary JSON from the results if available
RESULTS_JSON="$ROOT_DIR/reports/regression/results.json"
SUMMARY_JSON="$ROOT_DIR/reports/regression/summary.json"
if [ -f "$RESULTS_JSON" ]; then
  python3 - <<'PYEOF'
import json
import os
import sys
results_path = os.environ.get('RESULTS_JSON') or ''
summary_path = os.environ.get('SUMMARY_JSON') or ''
try:
    with open(results_path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
except Exception:
    data = {}
summary = {
    'total': data.get('total', 0),
    'matches': data.get('matches', 0),
    'mismatches': data.get('mismatches', 0)
}
try:
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, indent=2)
except Exception:
    pass
PYEOF
fi
