#!/usr/bin/env bash
# 冒烟演示：启动服务器 → 用简易 Python 客户端发 NICK/CHAT → 停服 → LLM mock 诊断
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p results server/uploads

PORT=9000
LOG_S="$ROOT/results/smoke_server.log"
LOG_D="$ROOT/results/smoke_diagnose.txt"
: > "$LOG_S"

echo "[demo] build..."
bash "$ROOT/scripts/build.sh"

echo "[demo] start server..."
( cd "$ROOT/server" && ./server -p "$PORT" -l "$LOG_S" ) &
SPID=$!
sleep 0.5

# 用 Python 标准库按协议发两帧，避免交互式 client 卡住
python3 - <<'PY'
import socket, struct, time, sys
HOST, PORT = "127.0.0.1", 9000

def send_frame(sock, typ, payload: bytes):
    header = b"CN" + bytes([1, typ]) + struct.pack("!I", len(payload))
    sock.sendall(header + payload)

def recv_frame(sock):
    hdr = b""
    while len(hdr) < 8:
        chunk = sock.recv(8 - len(hdr))
        if not chunk:
            return None
        hdr += chunk
    magic, ver, typ, length = hdr[0:2], hdr[2], hdr[3], struct.unpack("!I", hdr[4:8])[0]
    assert magic == b"CN"
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            break
        data += chunk
    return typ, data

s1 = socket.create_connection((HOST, PORT), timeout=5)
s2 = socket.create_connection((HOST, PORT), timeout=5)
# 读欢迎 SYS
recv_frame(s1); recv_frame(s2)
send_frame(s1, 3, b"Alice")  # NICK
send_frame(s2, 3, b"Bob")
time.sleep(0.2)
recv_frame(s1); recv_frame(s2)  # 欢迎等
send_frame(s1, 2, b"hello from smoke")  # CHAT
time.sleep(0.3)
# Bob 应能收到 CHAT
deadline = time.time() + 2
got_chat = False
s2.settimeout(0.5)
while time.time() < deadline:
    try:
        fr = recv_frame(s2)
    except socket.timeout:
        continue
    if not fr:
        break
    typ, data = fr
    print("s2 got", typ, data)
    if typ == 2:
        got_chat = True
        break
# 上传小文件到服务器 target=*
payload = b"smoke-demo-bytes"
meta = f"smoke.txt\t{len(payload)}\t*".encode()
send_frame(s1, 4, meta)  # FILE_META
time.sleep(0.1)
send_frame(s1, 5, payload)  # FILE_CHUNK
send_frame(s1, 6, b"ok")  # FILE_END
time.sleep(0.3)
s1.close(); s2.close()
print("SMOKE_CHAT_OK" if got_chat else "SMOKE_CHAT_FAIL")
sys.exit(0 if got_chat else 2)
PY
SMOKE_RC=$?

echo "[demo] stop server pid=$SPID"
kill "$SPID" 2>/dev/null || true
wait "$SPID" 2>/dev/null || true
sleep 0.2

echo "[demo] LLM mock diagnose..."
python3 "$ROOT/llm/diagnose.py" "$LOG_S" --mock -o "$LOG_D"

echo "[demo] server log tail:"
tail -n 30 "$LOG_S" || true
echo "[demo] uploads:"
ls -la "$ROOT/server/uploads" || true
echo "[demo] done rc=$SMOKE_RC  logs: $LOG_S  $LOG_D"
exit "$SMOKE_RC"
