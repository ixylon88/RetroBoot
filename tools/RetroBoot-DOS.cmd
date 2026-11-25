@echo off
setlocal DisableDelayedExpansion
if "%~1"=="" goto usage
set "operation="
set "resultfile=RetroBoot-DOS.vdi"
if /i "%~n0"=="RetroBoot-Countdown" (
    set "operation=--set-countdown"
    set "resultfile=RetroBoot-DOS-Countdown.vdi"
)
if /i "%~n0"=="RetroBoot-Countdown-Recovery" (
    set "operation=--recover-countdown"
    set "resultfile=RetroBoot-DOS-Recovered.vdi"
)
if /i "%~n0"=="RetroBoot-Recovery-Required" (
    set "operation=--require-recovery"
    set "resultfile=RetroBoot-DOS-Blocked.vdi"
)
if /i "%~n0"=="RetroBoot-Confirm-Verification" goto confirm
where py >nul 2>nul
if errorlevel 1 goto python
py -3 "%~dp0RetroBoot-DOS.pyz" "%~f1" --output "%~dp0%resultfile%" %operation%
goto result
:python
python "%~dp0RetroBoot-DOS.pyz" "%~f1" --output "%~dp0%resultfile%" %operation%
goto result
:confirm
set "reference=%~dp0RetroBoot-Reference.img"
if not "%~2"=="" set "reference=%~f2"
if not exist "%reference%" goto referenceMissing
where py >nul 2>nul
if errorlevel 1 goto confirmPython
py -3 "%~dp0RetroBoot-DOS.pyz" "%~f1" --confirm-verification "%reference%" --output "%~dp0RetroBoot-DOS-Ready.vdi"
goto result
:confirmPython
python "%~dp0RetroBoot-DOS.pyz" "%~f1" --confirm-verification "%reference%" --output "%~dp0RetroBoot-DOS-Ready.vdi"
:result
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo.
echo No output disk was created.
pause
exit /b 1
:referenceMissing
echo Missing pre-trial reference. Supply the reference disk as the second argument.
pause
exit /b 1
:usage
echo Drag the powered-off disk image onto "%~nx0".
pause
exit /b 1
