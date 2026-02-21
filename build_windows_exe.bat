@echo off
setlocal

echo [1/3] Checking Python...
python --version || goto :error

echo [2/3] Installing/Updating PyInstaller...
python -m pip install --upgrade pip pyinstaller || goto :error

echo [3/3] Building EXE...
pyinstaller --noconfirm ImportationReleveCompteurUniverselle.spec || goto :error

echo.
echo Build finished successfully.
echo Output: dist\ImportationReleveCompteurUniverselle.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
