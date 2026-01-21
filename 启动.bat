@echo off
REM 根据实际 Python 安装路径调整，如果已经在 PATH 中，也可以只写 python
set PYTHON_EXE=python

REM 项目目录
set WORK_DIR=E:\python_study\led播放控制器

cd /d "%WORK_DIR%"
echo Starting LED Controller Watchdog...
"%PYTHON_EXE%" watchdog.py
pause