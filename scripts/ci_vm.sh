#!/bin/sh
set -eu
PATH=/usr/local/bin:/usr/pkg/bin:/usr/sbin:/usr/bin:/bin:/opt/csw/bin:$PATH
export PATH
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; assert sys.version_info >= (3,10)' 2>/dev/null; then
            exec "$candidate" scripts/ci_native.py
        fi
    fi
done
echo 'The native VM needs Python 3.10 or newer.' >&2
exit 1
