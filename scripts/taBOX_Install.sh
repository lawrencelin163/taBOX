#!/bin/bash

cd "$(dirname "$0")/.."

sudo cp /home/$(whoami)/GitPS/taBOX/systemd/tabox-provision.service /etc/systemd/system/
sudo cp /home/$(whoami)/GitPS/taBOX/systemd/tabox-heartbeat.service /etc/systemd/system/
sudo cp /home/$(whoami)/GitPS/taBOX/systemd/openclaw-gateway.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable tabox-provision.service
sudo systemctl start tabox-provision.service
sudo systemctl enable tabox-heartbeat.service
sudo systemctl start tabox-heartbeat.service