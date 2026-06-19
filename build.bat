@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 安装打包依赖...
pip install -q pyinstaller requests pycryptodome

echo.
echo 开始打包...
pyinstaller --noconfirm --clean 哲风壁纸爬虫.spec

if %ERRORLEVEL% equ 0 (
    echo.
    echo 打包成功: dist\哲风壁纸爬虫.exe
) else (
    echo.
    echo 打包失败，错误码: %ERRORLEVEL%
)
pause
