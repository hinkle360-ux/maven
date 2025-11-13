#!/bin/bash
# Run a benchmark pack and write results to the bench reports directory.
# Usage: ./tools/run_bench.sh bench_core

set -euo pipefail
PACK="$1"
ROOT_DIR="$(dirname "$0")/.."
PACK_FILE="${ROOT_DIR}/tests/packs/${PACK}/${PACK}_inputs.jsonl"
OUT_DIR="${ROOT_DIR}/reports/bench"
OUT_FILE="${OUT_DIR}/${PACK}_results.jsonl"

mkdir -p "$OUT_DIR"
if [ ! -f "$PACK_FILE" ]; then
  echo "Pack file not found: $PACK_FILE" >&2
  exit 1
fi
echo "Running benchmark pack ${PACK}..."
python "${ROOT_DIR}/tests/run_pack.py" "${PACK_FILE}" | tee "$OUT_FILE"
echo "Results written to $OUT_FILE"