#!/bin/bash
# Install project pre-commit hooks
# This script installs pre-commit into a virtual environment (if necessary)
# and configures the Git hooks to run ruff, black and mypy on each commit.

set -euo pipefail

if ! command -v pre-commit >/dev/null 2>&1; then
  echo "pre-commit not found. Installing..."
  python3 -m pip install --user pre-commit
fi

pre-commit install
echo "Pre-commit hooks installed. Run 'pre-commit run --all-files' to check your code."