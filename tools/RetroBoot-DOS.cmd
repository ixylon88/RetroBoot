@echo off
setlocal
if "%~1"=="" goto usage
where py >nul 2>nul
if errorlevel 1 goto python
py -3 "%~dp0RetroBoot-DOS.pyz" "%~f1" --output "%~dp0RetroBoot-DOS.vdi"
goto result
:python
python "%~dp0RetroBoot-DOS.pyz" "%~f1" --output "%~dp0RetroBoot-DOS.vdi"
:result
if errorlevel 1 goto failed
echo.
echo RetroBoot-DOS.vdi is ready.
pause
exit /b 0
:failed
echo.
echo Disk preparation failed. Python 3 and VirtualBox are required.
pause
exit /b 1
:usage
echo Drag the installed MS-DOS virtual disk onto RetroBoot-DOS.cmd.
pause
exit /b 1
