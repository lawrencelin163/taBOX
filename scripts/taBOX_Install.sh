#!/bin/bash

cd "$(dirname "$0")/.."

sudo cp /home/$(whoami)/GitPS/taBOX/systemd/tabox-init.service /etc/systemd/system/
sudo cp /home/$(whoami)/GitPS/taBOX/systemd/tabox-heartbeat.service /etc/systemd/system/
sudo cp /home/$(whoami)/GitPS/taBOX/systemd/openclaw-gateway.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable tabox-init.service
sudo systemctl start tabox-init.service
sudo systemctl enable tabox-heartbeat.service