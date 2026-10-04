@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --name ArchiSearch --add-data "static;static" server.py
echo.
echo Termine : envoyez le dossier dist\ArchiSearch (zippe) a votre collegue.
pause