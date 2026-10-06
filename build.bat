@echo off
title Phantom TG Harvester — Build

echo.
echo  ==========================================
echo   PHANTOM TG HARVESTER — BUILD .EXE
echo  ==========================================
echo.

echo [1/4] Встановлення залежностей Python...
pip install pyinstaller httpx tiktok-uploader playwright -q
playwright install chromium

echo [2/4] Збірка React фронтенду...
cd frontend
call npm install -q
call npm run build
cd ..

echo [3/4] Пакування Python бекенду в backend.exe...
pyinstaller backend.spec --distpath dist-backend --workpath build-backend --noconfirm

echo [4/4] Створення Windows інсталятора .exe...
call npm install -q
call npx electron-builder --win --x64

echo.
echo  ==========================================
echo   ГОТОВО! Файл знаходиться в: dist-electron\
echo  ==========================================
echo.
pause
