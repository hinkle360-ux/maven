@echo off
rem Run the regression harness and log output by date
setlocal
rem Determine script and root directories
set SCRIPT_DIR=%~dp0
for %%I in ("%SCRIPT_DIR%\..") do set ROOT_DIR=%%~fI

rem Ensure the nightly regression report directory exists
set LOG_DIR=%ROOT_DIR%\reports\nightly_regression
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

rem Compute the date stamp (YYYYMMDD) using PowerShell for portability
for /f %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set DATE=%%a

set LOG_FILE=%LOG_DIR%\regression_%DATE%.log

rem Run the regression harness and capture stdout/stderr
python "%ROOT_DIR%\tools\regression_harness.py" > "%LOG_FILE%" 2>&1
echo Regression run complete: %LOG_FILE%

rem Generate a summary JSON if the results.json exists
set RESULTS_JSON=%ROOT_DIR%\reports\regression\results.json
set SUMMARY_JSON=%ROOT_DIR%\reports\regression\summary.json

if exist "%RESULTS_JSON%" (
    python - <<"PYEOF"
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
)

endlocal