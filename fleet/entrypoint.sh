#!/bin/sh
# Starts sshd plus the one service this host's role runs, then idles.
# Env vars (set per host by scripts/generate_fleet.py):
#   ROLE          web | app | db
#   SKIP_SERVICE  1 = do not start the role's service (simulates a crashed service)
#   BROKEN_SSH    1 = do not start sshd (simulates an unreachable host)
#   FILL_MB       megabytes to write into the small /data volume (simulates a filling disk)
set -eu

ROLE="${ROLE:-web}"

if [ "${BROKEN_SSH:-0}" != "1" ]; then
    /usr/sbin/sshd
fi

if [ "${SKIP_SERVICE:-0}" != "1" ]; then
    case "$ROLE" in
        web) nginx ;;
        app) python3 -m http.server 8080 --directory /srv >/dev/null 2>&1 & ;;
        db)  socat TCP-LISTEN:5432,fork,reuseaddr SYSTEM:true >/dev/null 2>&1 & ;;
    esac
fi

if [ -n "${FILL_MB:-}" ]; then
    dd if=/dev/zero of=/data/fill.bin bs=1M count="${FILL_MB}" status=none
fi

exec sleep infinity
