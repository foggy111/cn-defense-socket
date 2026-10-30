#!/usr/bin/env bash
# 一键编译 server + client（WSL / Linux）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "[build] ROOT=$ROOT"
make -C server clean all
make -C client clean all
echo "[build] OK"
ls -la server/server client/client
