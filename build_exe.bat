@echo off
cd /d "%~dp0"

echo Installing / updating PyInstaller...
python -m pip install --upgrade pip
python -m pip install pyinstaller

echo Building exe...
pyinstaller --onefile --windowed --name "Khanh_Mail_Checker_V46_AvatarSplash" --icon "app_icon.ico" --add-data "app_avatar.png;." "Khanh_Mail_Checker_V46_AvatarSplash.pyw"

echo.
echo Done.
echo EXE: dist\Khanh_Mail_Checker_V46_AvatarSplash.exe
pause
