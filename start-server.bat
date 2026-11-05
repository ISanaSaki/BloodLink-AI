@echo off
cd /d "%~dp0frontend"

where python >nul 2>nul
if %errorlevel%==0 (
  start "Hamkhoon Server" python -m http.server 5500
) else (
  start "Hamkhoon Server" py -m http.server 5500
)

timeout /t 2 /nobreak >nul
start "" http://localhost:5500
