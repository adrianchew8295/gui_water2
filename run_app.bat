@echo off
title Gui_Water2 - 自动同步与启动中枢
cd /d "%USERPROFILE%\Desktop\gui_water2"

echo =======================================================
echo    [1/2] 正在从 GitHub 自动同步最新代码 (Auto Pull)...
echo =======================================================
git pull origin main

echo.
echo =======================================================
echo    [2/2] 正在启动 Market Data Hub 看板...
echo =======================================================
python -m streamlit run app.py

pause