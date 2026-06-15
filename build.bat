@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 安装打包依赖...
pip install -q pyinstaller requests

echo.
echo 开始打包...
pyinstaller --noconfirm --clean ^
  --onefile ^
  --windowed ^
  --name "哲风壁纸爬虫" ^
  --hidden-import=爬虫 ^
  --hidden-import=爬虫_gui ^
  --collect-all=requests ^
  main.py

if %ERRORLEVEL% equ 0 (
    echo.
    echo 打包成功: dist\哲风壁纸爬虫.exe
) else (
    echo.
    echo 打包失败，错误码: %ERRORLEVEL%
)
pause
