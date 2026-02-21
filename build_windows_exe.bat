@echo off
setlocal
python -m pip install --upgrade pip
pip install pyinstaller
pyinstaller --noconfirm --onefile --name ImportationReleveCompteurUniverselle --add-data "web;web" importation_releve_compteur_universelle.py
echo.
echo Build finished: dist\ImportationReleveCompteurUniverselle.exe
endlocal
