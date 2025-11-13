@echo off
rem Simple launcher for the Maven chat interface on Windows.
rem
rem This script locates a suitable Python 3.11 interpreter, adds the Maven
rem project root to PYTHONPATH so that package imports (e.g. 'api.utils') work,
rem and then launches the chat interface via Python's module system.  No
rem PowerShell is required and you can simply double‑click this file.

setlocal

rem Attempt to use the py launcher for Python 3.11; fall back to plain python.
set "PYEXE=py -3.11"
%PYEXE% --version >nul 2>&1 || set "PYEXE=python"

rem Compute the absolute path to this script's directory (the Maven project root).
set "SCRIPT_DIR=%~dp0"

rem Ensure that the Maven project root is on PYTHONPATH so imports like 'api'
rem resolve correctly when launching modules below.
set "PYTHONPATH=%SCRIPT_DIR%"

rem Launch the chat interface as a module.  There is no nested 'maven'
rem package in this build, so run the ``ui.maven_chat`` package directly.
%PYEXE% -m ui.maven_chat %*

rem Keep the console window open after execution so the user can read the output.
pause