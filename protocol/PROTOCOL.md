# 应用层协议说明（CN-Chat）

课程：《计算机网络技术》代码 **1960193**  
单位：天津理工大学华信软件学院  
适用：甲（服务器）/ 乙（客户端）共用

## 1. 设计目标

TCP 提供**字节流**可靠传输，但不提供消息边界。本协议在 TCP 之上定义**定长帧头 + 变长载荷**，用于：

- 多客户端文字聊天（广播）
- 点对点或上传服务器的文件传输
- 系统提示、在线列表、心跳

## 2. 帧格式（二进制）

| 字段 | 长度 | 说明 |
|------|------|------|
| magic | 2 B | 固定 `'C''N'` (0x43 0x4E) |
| version | 1 B | 当前为 `1` |
| type | 1 B | 见类型表 |
| length | 4 B | 载荷长度，**网络字节序**（大端） |
| payload | length B | UTF-8 文本或原始二进制 |

最大载荷：`1 MiB`（实现中拒绝更大帧，减轻内存耗尽风险）。

```
+------+---------+------+----------+------------------+
| CN   | version | type | length   | payload          |
| 2B   | 1B      | 1B   | 4B (BE)  | length bytes     |
+------+---------+------+----------+------------------+
```

## 3. 类型表

| 值 | 名称 | 方向 | 载荷约定 |
|----|------|------|----------|
| 1 | SYS | S→C / 内部 | 任意提示文本 |
| 2 | CHAT | C→S / S→C | 上行：`message`；下行：`from\\tmessage` |
| 3 | NICK | C→S | `nick`（1..32，非 `*`） |
| 4 | FILE_META | C→S→C | 上行：`filename\\tsize\\ttarget`；下行：`sender\\tfilename\\tsize\\ttarget` |
| 5 | FILE_CHUNK | C→S→C | 原始二进制分块 |
| 6 | FILE_END | C→S→C | 状态文本，如 `ok`；下行可带 `sender\\tfilename\\tstatus\\ttarget` |
| 7 | LIST | C→S / S→C | 上行空；下行 `nick1,nick2,...` |
| 8 | PING | C→S | 任意 |
| 9 | PONG | S→C | 回显 |

`target`：对端昵称，或 `*` 表示**上传到服务器**目录 `server/uploads/`（文件名：`{sender}_{filename}`）。

## 4. 典型时序

### 4.1 登录与聊天

```
ClientA                    Server                     ClientB
   |--- NICK "Alice" ------>|                            |
   |<-- SYS 欢迎 -----------|                            |
   |                        |--- SYS Alice加入 --------->|
   |--- CHAT "hi" --------->|                            |
   |                        |--- CHAT Alice\\thi ------->|
```

### 4.2 客户端 → 客户端文件

```
A: FILE_META(file,size,B) -> Server -> FILE_META 转发给 B
A: FILE_CHUNK*            -> Server -> 转发给 B
A: FILE_END               -> Server -> 转发给 B
B 本地写 recv_{A}_{file}
```

### 4.3 上传服务器

`target=*` 时，Server 打开 `uploads/{sender}_{filename}`，写入 CHUNK，END 后广播 SYS。

## 5. 粘包 / 半包

接收端必须：**先读满 8 字节帧头 → 按 length 再读满载荷**。禁止假设一次 `recv` 对应一帧。发送端用循环 `send` 保证发完。

## 6. 字节序

`length` 使用 `htonl`/`ntohl`。magic/version/type 为单字节或字符，无端序问题。

## 7. 与课程知识点映射

| 知识点 | 在本协议中的体现 |
|--------|------------------|
| TCP 面向连接 | connect/accept 之后才交换帧 |
| 可靠传输 | 文件完整性依赖 TCP；应用层用 size 校验进度 |
| 端口与多路复用 | 服务器 :9000，多客户端多 fd |
| 应用层协议 | 自定义 CN 帧 |
| 并发 | 服务器 thread-per-client |

## 8. 实现位置

- 公共头：`common/protocol.hpp`
- 服务器：`server/server.cpp`（甲）
- 客户端：`client/client.cpp`（乙）
