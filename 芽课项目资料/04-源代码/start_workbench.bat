@echo off
rem PM Learning Workbench - desktop launcher
set PY=C:\Users\13024\.workbuddy\binaries\python\versions\3.13.12\python.exe
set DIR=C:\Users\13024\WorkBuddy\pm-learning-workbench

netstat -ano | findstr :8848 | findstr LISTENING >nul
if errorlevel 1 (
  cd /d %DIR%
  start "WB-Server" /min "%PY%" server.py
  ping -n 3 127.0.0.1 >nul
)

start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --app=http://127.0.0.1:8848/
