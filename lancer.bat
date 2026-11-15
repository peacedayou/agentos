@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === AgentOS ===
echo 1. Nouvelle mission
echo 2. Conversation
echo 3. Mode systeme (daemon)
set /p c=Choix : 
if "%c%"=="1" (set /p m=Mission : & python -m agentos run "%m%")
if "%c%"=="2" python -m agentos chat
if "%c%"=="3" python -m agentos daemon
pause
