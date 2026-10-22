@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo [错误] 未找到虚拟环境 .venv。
    echo 请先执行：
    echo   python -m venv .venv
    echo   .venv\Scripts\python -m pip install -r requirements.txt
    echo 然后重新运行 run.bat。
    pause
    exit /b 1
)

if not exist "main.py" (
    echo [错误] 未找到 main.py，请在项目根目录运行本脚本。
    pause
    exit /b 1
)

echo 正在启动 BiliDownloader（.venv\Scripts\pythonw.exe main.py）...
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0
