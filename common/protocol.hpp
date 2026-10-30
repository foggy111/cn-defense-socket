// 计算机网络技术 课程设计 — 应用层帧协议定义（甲乙共用）
// 课程代码: 1960193 | 华信软件学院
#pragma once
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/socket.h>
#include <errno.h>

namespace cn {

// 帧类型
enum class FrameType : uint8_t {
    SYS        = 1,  // 系统消息 / 错误 / 提示
    CHAT       = 2,  // 聊天消息
    NICK       = 3,  // 设置昵称 / 登录
    FILE_META  = 4,  // 文件元信息
    FILE_CHUNK = 5,  // 文件分块数据
    FILE_END   = 6,  // 文件传输结束
    LIST       = 7,  // 在线用户列表请求/响应
    PING       = 8,
    PONG       = 9,
};

#pragma pack(push, 1)
struct FrameHeader {
    char     magic[2];   // 'C','N'
    uint8_t  version;    // 1
    uint8_t  type;       // FrameType
    uint32_t length;     // payload 字节数（网络序）
};
#pragma pack(pop)

static constexpr size_t HEADER_SIZE = sizeof(FrameHeader);
static constexpr uint8_t PROTO_VER = 1;
static constexpr size_t MAX_PAYLOAD = 1024 * 1024; // 1MB/帧，防止恶意超大帧

inline bool send_all(int fd, const void* buf, size_t n) {
    const char* p = static_cast<const char*>(buf);
    size_t left = n;
    while (left > 0) {
        ssize_t w = ::send(fd, p, left, MSG_NOSIGNAL);
        if (w < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        if (w == 0) return false;
        p += w;
        left -= static_cast<size_t>(w);
    }
    return true;
}

inline bool recv_all(int fd, void* buf, size_t n) {
    char* p = static_cast<char*>(buf);
    size_t left = n;
    while (left > 0) {
        ssize_t r = ::recv(fd, p, left, 0);
        if (r < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        if (r == 0) return false; // peer closed
        p += r;
        left -= static_cast<size_t>(r);
    }
    return true;
}

inline bool send_frame(int fd, FrameType type, const void* payload, uint32_t len) {
    if (len > MAX_PAYLOAD) return false;
    FrameHeader h{};
    h.magic[0] = 'C';
    h.magic[1] = 'N';
    h.version = PROTO_VER;
    h.type = static_cast<uint8_t>(type);
    h.length = htonl(len);
    if (!send_all(fd, &h, HEADER_SIZE)) return false;
    if (len > 0 && payload) {
        if (!send_all(fd, payload, len)) return false;
    }
    return true;
}

inline bool send_frame(int fd, FrameType type, const std::string& s) {
    return send_frame(fd, type, s.data(), static_cast<uint32_t>(s.size()));
}

struct Frame {
    FrameType type{FrameType::SYS};
    std::string payload;
};

inline bool recv_frame(int fd, Frame& out) {
    FrameHeader h{};
    if (!recv_all(fd, &h, HEADER_SIZE)) return false;
    if (h.magic[0] != 'C' || h.magic[1] != 'N') return false;
    if (h.version != PROTO_VER) return false;
    uint32_t len = ntohl(h.length);
    if (len > MAX_PAYLOAD) return false;
    out.type = static_cast<FrameType>(h.type);
    out.payload.assign(len, '\0');
    if (len > 0) {
        if (!recv_all(fd, &out.payload[0], len)) return false;
    }
    return true;
}

// 载荷约定（文本 UTF-8）:
// NICK:       nick
// CHAT:       from\tnick_or_empty\tmessage   服务端广播时带 from；客户端发送可只写 message（服务端补 from）
//             客户端上行: message
//             服务端下行: from\tmessage
// FILE_META:  sender\tfilename\tfilesize\ttarget_nick_or_*
// FILE_CHUNK: 原始二进制
// FILE_END:   sender\tfilename\tstatus(ok|fail)\ttarget
// SYS:        任意提示文本
// LIST:       上行空；下行 nick1,nick2,...

inline std::string type_name(FrameType t) {
    switch (t) {
        case FrameType::SYS: return "SYS";
        case FrameType::CHAT: return "CHAT";
        case FrameType::NICK: return "NICK";
        case FrameType::FILE_META: return "FILE_META";
        case FrameType::FILE_CHUNK: return "FILE_CHUNK";
        case FrameType::FILE_END: return "FILE_END";
        case FrameType::LIST: return "LIST";
        case FrameType::PING: return "PING";
        case FrameType::PONG: return "PONG";
        default: return "UNKNOWN";
    }
}

} // namespace cn
