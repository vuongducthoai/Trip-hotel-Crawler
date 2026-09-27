@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === Trip Hotel Data - tao installer Windows ===
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
