@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 找不到项目虚拟环境，请按 README 的安装步骤配置。
  pause
  exit /b 1
)
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" "scripts\start.py"
set "taskExitCode=%errorlevel%"
pause
exit /b %taskExitCode%
