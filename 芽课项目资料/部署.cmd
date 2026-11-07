@echo off
rem 芽课工作台 · 一键部署到腾讯云 CloudBase
setlocal
set DIR=%~dp0
set ENV_ID=yake-pm-learn-d8gj30hst985e4f14
set TCB=%USERPROFILE%\.dsh-tools\cloudbase\tcb.cmd
set SRC=%DIR%09-线上部署\芽课工作台-线上数据版.html

if not exist "%SRC%" ( echo 缺少 %SRC% & exit /b 1 )
if not exist "%DIR%09-线上部署\deploy" mkdir "%DIR%09-线上部署\deploy"
copy /Y "%SRC%" "%DIR%09-线上部署\deploy\index.html" >nul

echo 部署到 %ENV_ID% ...
call "%TCB%" hosting deploy "%DIR%09-线上部署\deploy" -e %ENV_ID% --safe --verify
echo 完成: https://%ENV_ID%-1491333553.tcloudbaseapp.com/
