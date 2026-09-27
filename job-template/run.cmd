@echo off
setlocal
set "JOB_ROOT=%~dp0"
set "JOB_ACTION=%~1"
if "%JOB_ACTION%"=="" set "JOB_ACTION=check"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "$ErrorActionPreference='Stop'; $env:PSModulePath=$PSHOME+'\Modules'; $r=$env:JOB_ROOT; $m=Get-Content -LiteralPath ($r+'runtime\manifest.json') -Raw | ConvertFrom-Json; if($m.target -ne 'windows-x64'){throw 'This job runtime is for another OS/CPU. Download a Windows x64 job.'}; $a=$m.artifacts | Where-Object {$_.component -eq 'python'}; $archive=$r+'runtime\archives\python.zip'; if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $a.sha256){throw 'Python archive checksum mismatch'}; $p=$r+'runtime\python'; if(!(Test-Path -LiteralPath ($p+'\python.exe'))){Expand-Archive -LiteralPath $archive -DestinationPath $p -Force}; Get-ChildItem -LiteralPath $p -Filter '*._pth' | ForEach-Object {$text=Get-Content -LiteralPath $_.FullName -Raw; if(!$text.Contains('../../scripts')){Add-Content -LiteralPath $_.FullName -Value '../../scripts' -Encoding ascii}}; $env:PYTHONIOENCODING='utf-8'; $env:PYTHONDONTWRITEBYTECODE='1'; & ($p+'\python.exe') ($r+'scripts\bootstrap.py') $env:JOB_ACTION; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
