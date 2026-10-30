# CN-Chat：C++ TCP Socket 聊天 + 文件传输 + LLM 日志诊断

> 天津理工大学 · 华信软件学院  
> 课程：《计算机网络技术》**1960193**  
> 学生：牛昭凯 及团队占位 **甲 / 乙 / 丙 / 丁**  
> 指导教师：（空白，请填写）

本仓库是四人课程答辩完整工程：可编译运行的服务器/客户端、应用层协议、设计说明书，以及大语言模型辅助诊断模块。

---

## 四人分工（务必按此陈述）

| 角色 | 职责 | 主要路径 |
|------|------|----------|
| **甲** | TCP 多客户端服务器（监听、广播、文件中继/上传、日志） | `server/`、`common/protocol.hpp` |
| **乙** | TCP 交互式客户端（`/nick /say /sendfile /quit`） | `client/` |
| **丙** | 选题与设计说明书、协议文档、测试文字 | `docs/`、`protocol/` |
| **丁** | LLM 诊断、答辩提纲、演示脚本协助 | `llm/`、`docs/04_答辩陈述提纲.md` |

细节见 [`docs/03_分工与进度.md`](docs/03_分工与进度.md)。

---

## 环境要求

- Linux 或 **Windows WSL**（推荐 Ubuntu）
- `g++`（支持 C++17）、`make`、`python3`
- 无需额外 pip 包（LLM 仅用标准库）

---

## 推荐放置路径

本地 Windows 侧建议：

```text
C:\Users\niu\OS\cn-defense-socket
```

WSL 中对应：

```bash
cd /mnt/c/Users/niu/OS/cn-defense-socket
```

当前构建机上的绝对路径：

```text
/workspace/cn-defense-socket
```

---

## 一键编译（WSL / Linux）

```bash
cd /mnt/c/Users/niu/OS/cn-defense-socket   # 或 cd /workspace/cn-defense-socket
bash scripts/build.sh
```

等价：

```bash
make -C server
make -C client
# 产物: server/server  client/client
```

---

## 运行演示

### 方式 A：一键冒烟（推荐验收）

```bash
bash scripts/demo.sh
```

将：

1. 编译 server/client  
2. 后台启动服务器  
3. 用协议帧完成 NICK/CHAT/文件上传  
4. 停止服务器  
5. 对日志跑 LLM **mock** 诊断  

产物：

- `results/smoke_server.log`
- `results/smoke_diagnose.txt`
- `server/uploads/` 下上传样例

### 方式 B：双终端手工演示

```bash
# 终端 1 — 甲
cd server
./server -p 9000 -l ../results/demo_server.log

# 终端 2 — 乙
cd client
./client -h 127.0.0.1 -p 9000
# 输入:
# /nick Alice
# hello everyone

# 终端 3 — 乙
cd client
./client -h 127.0.0.1 -p 9000
# /nick Bob
# /list
# /say hi Alice
# /sendfile ../samples/demo.txt *
# /sendfile ../samples/demo.txt Alice
# /quit
```

客户端命令：

| 命令 | 说明 |
|------|------|
| `/nick <名>` | 设置昵称 |
| `/say <消息>` 或直接输入 | 群聊 |
| `/list` | 在线用户 |
| `/sendfile <路径> [目标]` | 发文件；目标省略或 `*` = 上传服务器 |
| `/ping` | 心跳 |
| `/quit` | 退出 |

---

## LLM 诊断（丁）

```bash
# 离线 mock（无 API Key，答辩保底）
python3 llm/diagnose.py samples/sample_chat_log.txt --mock

# 对冒烟日志
python3 llm/diagnose.py results/smoke_server.log --mock -o results/smoke_diagnose.txt

# 真实 OpenAI 兼容 API
export OPENAI_API_KEY='你的密钥'
export OPENAI_BASE_URL='https://api.openai.com/v1'   # 可换代理/兼容端点
export OPENAI_MODEL='gpt-4o-mini'
python3 llm/diagnose.py results/smoke_server.log
```

---

## 文档索引

| 文件 | 内容 |
|------|------|
| [`docs/01_选题说明.md`](docs/01_选题说明.md) | 选题与课程要求对应 |
| [`docs/02_设计说明书.md`](docs/02_设计说明书.md) | **详细原理 + 设计步骤 + 测试**（说明书主体） |
| [`docs/03_分工与进度.md`](docs/03_分工与进度.md) | 甲乙丙丁任务与进度 |
| [`docs/04_答辩陈述提纲.md`](docs/04_答辩陈述提纲.md) | 丁用答辩提纲 |
| [`protocol/PROTOCOL.md`](protocol/PROTOCOL.md) | 二进制帧协议 |

---

## 协议速览

帧：`magic('C','N') + version(1) + type(u8) + length(u32 BE) + payload`  

类型：`SYS CHAT NICK FILE_META FILE_CHUNK FILE_END LIST PING PONG`  

服务器默认 **`0.0.0.0:9000`**。上传目录：`server/uploads/`。

---

## 打包提示

可将整个目录打成 zip 拷到 Windows：

```bash
cd /workspace && zip -r cn-defense-socket.zip cn-defense-socket \
  -x 'cn-defense-socket/server/server' -x 'cn-defense-socket/client/client' \
  -x 'cn-defense-socket/**/*.log' -x 'cn-defense-socket/**/__pycache__/*'
# 再复制到 C:\Users\niu\OS\
```

（二进制建议在目标 WSL 上重新 `bash scripts/build.sh`。）

---

## 许可证与声明

仅供课程设计与答辩使用。请勿用于未授权网络攻击或骚扰。
