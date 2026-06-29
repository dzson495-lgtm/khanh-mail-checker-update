@echo off
cd /d "%~dp0"

echo Starting Khanh Mail Checker V46...
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0Khanh_Mail_Checker_V46_AvatarSplash.pyw"
) else (
    python "%~dp0Khanh_Mail_Checker_V46_AvatarSplash.pyw"
    pause
)
