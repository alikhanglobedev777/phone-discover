@echo off
setlocal
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Python environment missing. Run "py dev.py" from the project root first.
  exit /b 1
)
".venv\Scripts\python.exe" manage.py refresh_phone_prices --scheduled
exit /b %ERRORLEVEL%
