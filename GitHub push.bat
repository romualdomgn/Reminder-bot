@'
@echo off
cd /d "%~dp0"

git add -A
git diff --cached --quiet
if %errorlevel%==0 (
    echo Nothing to commit.
    pause
    exit /b
)

set /p MSG=Commit message (Enter = Update): 
if "%MSG%"=="" set MSG=Update

git commit -m "%MSG%"
git push

pause
'@ | Set-Content push.bat -Encoding ascii