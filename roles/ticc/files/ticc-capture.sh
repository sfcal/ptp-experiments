#!/bin/bash
# Managed by Ansible (roles/ticc). Capture worker for ticc-capture@.service.
# One timestamped file per run; append-only, so nothing is ever overwritten.
set -euo pipefail

log=/var/log/ticc/${1:?usage: ticc-capture.sh <name>}_$(date +%Y%m%d-%H%M%S).log

# Single open shared by stty and cat: the open's DTR pulse reboots the TICC,
# so each log starts with its config banner. raw + -echo: never write back
# to the port (stray bytes would hit the TICC's config parser).
exec < /dev/ticc
stty 115200 raw -echo
exec cat >> "$log"
