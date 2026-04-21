@echo off
set TARGET_HOST=KL
scp app.py tabox_config.py taServer_API.py tabox_heartbeat.py taBOX.json yf@%TARGET_HOST%:/home/yf/GitPS/taBOX/