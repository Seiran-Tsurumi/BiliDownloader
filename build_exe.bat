@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 .venv，请先执行：
    echo   python -m venv .venv
    echo   .venv\Scripts\python -m pip install -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller BiliDownloader.spec --noconfirm
set "build_exit=%errorlevel%"

if not "%build_exit%"=="0" (
    echo [构建失败] PyInstaller 退出码: %build_exit%
    pause
    exit /b %build_exit%
)

echo [构建成功] 输出文件: dist\BiliDownloader.exe
pause
