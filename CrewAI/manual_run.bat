@echo off
REM HIKMAH manual run helper (Windows)
REM Usage:  manual_run.bat [project] [--demo|--dry-run]
REM   manual_run.bat dataarch --demo
REM   manual_run.bat all
cd /d "%~dp0"
if "%~1"=="" (
  python run_now.py all --demo
) else (
  python run_now.py %*
)
pause
