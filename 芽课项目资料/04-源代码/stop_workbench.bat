@echo off
setlocal
rem ============================================================
rem  Sprout (PM Learning Workbench) - stop the local server
rem  Kills whatever process is LISTENING on port 8848.
rem ============================================================
set "PORT=8848"
set "FOUND="

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    if not defined FOUND (
        set "FOUND=1"
        echo Killing PID %%p listening on port %PORT% ...
        taskkill /PID %%p /F >nul 2>&1
    )
)

if not defined FOUND (
    echo No process listening on port %PORT% - nothing to stop.
)
pause
