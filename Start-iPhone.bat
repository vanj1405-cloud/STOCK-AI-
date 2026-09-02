@echo off
cd /d "%~dp0"

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address" /c:"IPv4 Address."') do (
    set IP=%%a
    goto :found
)

:found
set IP=%IP: =%

echo.
echo ===============================================
echo   STOCK AI - IPHONE MODE
echo ===============================================
echo.
echo Keep this window open.
echo Make sure the iPhone and this PC are on the SAME Wi-Fi.
echo.
echo On your iPhone, open Safari and enter:
echo.
echo     http://%IP%:8501
echo.
echo If Windows Firewall asks for permission, allow Private networks.
echo ===============================================
echo.

python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
pause
