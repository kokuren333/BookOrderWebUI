@echo off
setlocal
rem BookOrder CLI. The first call unpacks the bundled Python; later calls reuse it (checksums are cached).
if exist "%~dp0runtime\manifest.json" (
  if not exist "%~dp0runtime\python\python.exe" (
    call "%~dp0run.cmd" check
    if errorlevel 1 exit /b 1
  )
  "%~dp0runtime\python\python.exe" "%~dp0scripts\cli.py" %*
) else (
  python "%~dp0scripts\cli.py" %*
)
exit /b %ERRORLEVEL%
