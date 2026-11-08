@echo off
setlocal
if "%~1"=="" (
  echo Usage: install-sm86-trex.bat "FULL_PATH_TO_MINECRAFT_GAME_DIRECTORY"
  echo Experimental: requires the runtime's remix-sdk\.trex folder to exist.
  exit /b 2
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-sm86-trex.ps1" -Action Install -GameDir "%~1"
exit /b %ERRORLEVEL%
