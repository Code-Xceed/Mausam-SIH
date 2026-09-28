@echo off
rem Detached release-APK build (survives the calling shell). Log: apk_build.log
cd /d %~dp0
start /b "" cmd /c "flutter build apk --release --split-per-abi --dart-define=BACKEND_URL=https://mausam-nextgen.onrender.com > apk_build.log 2>&1"
