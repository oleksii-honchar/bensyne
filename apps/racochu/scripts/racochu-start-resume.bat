@echo off
REM Launch racochu in resume mode from any working directory (e.g. a desktop shortcut).
REM Changes to the app root (parent of this scripts folder) so npm resolves package.json.

setlocal
cd /d "%~dp0.." || exit /b 1

npm run start:resume
set EXITCODE=%ERRORLEVEL%

REM Keep the window open on failure so the error is readable before it closes.
if not "%EXITCODE%"=="0" (
  echo.
  echo racochu exited with code %EXITCODE%. Press any key to close...
  pause >nul
)
endlocal & exit /b %EXITCODE%
