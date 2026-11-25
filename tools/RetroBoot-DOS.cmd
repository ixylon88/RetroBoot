@echo off
setlocal DisableDelayedExpansion
if "%~1"=="" goto usage
set "operation="
set "resultfile=RetroBoot-DOS.vdi"
if /i "%~n0"=="RetroBoot-Countdown" (
    set "operation=--set-countdown"
    set "resultfile=RetroBoot-DOS-Countdown.vdi"
)
where py >nul 2>nul
if errorlevel 1 goto python
py -3 "%~dp0RetroBoot-DOS.pyz" "%~f1" --output "%~dp0%resultfile%" %operation%
goto result
:python
python "%~dp0RetroBoot-DOS.pyz" "%~f1" --output "%~dp0%resultfile%" %operation%
:result
if errorlevel 1 goto failed
echo.
echo %resultfile% is ready.
pause
exit /b 0
:failed
echo.
echo No output disk was created.
pause
exit /b 1
:usage
echo Drag the powered-off disk image onto "%~nx0".
pause
exit /b 1
