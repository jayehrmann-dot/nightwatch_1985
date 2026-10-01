#!/usr/bin/env bash
# Launch Nightwatch 1985 in the current terminal.
cd "$(dirname "$0")" || exit 1
exec python3 -m nightwatch "$@"
