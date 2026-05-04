@echo off
:: Upload selected taBOX files from local folder to YF target path (force overwrite)
:: One SFTP connection, password entered once

(
echo lcd "."
echo put tabox_config.py /home/yf/GitPS/taBOX/tabox_config.py
echo put tabox_heartbeat.py /home/yf/GitPS/taBOX/tabox_heartbeat.py
echo put taBOX_MR408001.json /home/yf/GitPS/taBOX/taBOX_MR408001.json
echo put taLog.py /home/yf/GitPS/taBOX/taLog.py
echo put taServer_API.py /home/yf/GitPS/taBOX/taServer_API.py
echo put taSystemCmd.py /home/yf/GitPS/taBOX/taSystemCmd.py
echo put taWifi.py /home/yf/GitPS/taBOX/taWifi.py
) > _sftp_batch.txt

sftp yf@YF < _sftp_batch.txt

del _sftp_batch.txt
echo.
echo Upload to YF complete from current directory
