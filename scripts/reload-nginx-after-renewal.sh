#!/bin/sh
# Certbot deploy hook, executed on the Pi host after a successful renewal.
set -eu
cd /home/pi/dev/rpi-server
/usr/bin/docker compose -f docker-compose.yaml exec -T reverse nginx -t
/usr/bin/docker compose -f docker-compose.yaml exec -T reverse nginx -s reload
