@echo off

set ZIP_NAME=taBOX_20260421-1755.zip

echo Generating %ZIP_NAME% ,  .....

tar -a -c -f "%ZIP_NAME%" ^
  .venv scripts static systemd Temp templates ^
  app.py requirements.txt tabox_config.py tabox_heartbeat.py taBOX.json taServer_API.py

if errorlevel 1 (
  echo ZIP failed.
) else (
  echo Done: %ZIP_NAME%
)
