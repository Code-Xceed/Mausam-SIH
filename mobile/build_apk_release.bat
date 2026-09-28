@echo off
rem Detached release-APK build (survives the calling shell). Log: apk_build.log
rem The trailing EXIT line records the real flutter exit code (0 = success).
cd /d %~dp0
start /b "" cmd /v:on /c "flutter build apk --release --split-per-abi --dart-define=BACKEND_URL=https://mausam-nextgen.onrender.com > apk_build.log 2>&1 & echo EXIT=!ERRORLEVEL! >> apk_build.log"
