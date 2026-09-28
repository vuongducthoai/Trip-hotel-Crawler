@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === Trip Hotel Data - tao installer Windows ===
echo.
echo [0/2] Dong cac tien trinh cua app dang chay (neu co)...
taskkill /f /im "Trip Hotel Data.exe" >nul 2>&1
taskkill /f /im "tool-crawler-backend.exe" >nul 2>&1
taskkill /f /im "Tool Crawler Trip.exe" >nul 2>&1
timeout /t 2 /nobreak >nul
if exist "dist\win-unpacked" rmdir /s /q "dist\win-unpacked" >nul 2>&1
echo.
echo [1/2] Dong goi backend Python (PyInstaller)...
call npm run build:backend
if errorlevel 1 goto :loi
echo.
echo [2/2] Tao installer NSIS (electron-builder)...
call npx electron-builder --win nsis
if errorlevel 1 goto :loi
echo.
echo === XONG. File setup nam trong thu muc dist ===
dir /b dist\*.exe
start "" "dist"
pause
exit /b 0
:loi
echo.
echo *** BUILD LOI - xem thong bao phia tren ***
pause
exit /b 1
