@echo off
rem One-click Windows launcher: run the doctor first, then start the product
rem and open the browser. ASCII-only on purpose so every console codepage reads it.
setlocal
cd /d "%~dp0"

set "DOCTOR_ONLY="
if /I "%~1"=="--doctor" set "DOCTOR_ONLY=1"

where uv >nul 2>nul
if not errorlevel 1 goto use_uv

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
%PY% app\server.py --doctor
if errorlevel 1 goto blocked
if defined DOCTOR_ONLY goto done
%PY% app\server.py --open
goto done

:use_uv
uv run --locked python app\server.py --doctor
if errorlevel 1 goto blocked
if defined DOCTOR_ONLY goto done
uv run --locked python app\server.py --open
goto done

:blocked
echo.
echo Startup stopped: fix the items marked as failed above, then run this file again.
pause
exit /b 2

:done
if not defined DOCTOR_ONLY pause
endlocal
