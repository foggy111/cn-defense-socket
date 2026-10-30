// 甲 — TCP 多客户端聊天/文件中继服务器
#include <ctime>
// 课程《计算机网络技术》1960193 | 天津理工大学华信软件学院
// 学生占位：甲（可填：牛昭凯）
#include "../common/protocol.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <netinet/in.h>
#include <sys/stat.h>
#include <sys/types.h>

using namespace cn;

static std::atomic<bool> g_running{true};
static std::mutex g_mu;
static std::ofstream g_log;

struct Client {
    int fd{-1};
    std::string nick;
    std::string addr;
};

static std::map<int, Client> g_clients; // fd -> Client

static void log_line(const std::string& s) {
    auto now = std::chrono::system_clock::now();
    auto t = std::chrono::system_clock::to_time_t(now);
    char buf[64];
    std::strftime(buf, sizeof(buf), "%F %T", std::localtime(&t));
    std::string line = std::string("[") + buf + "] " + s;
    std::cout << line << std::endl;
    if (g_log.is_open()) {
        g_log << line << std::endl;
        g_log.flush();
    }
}

static void ensure_uploads() {
    mkdir("uploads", 0755);
    // 兼容从项目根或 server/ 启动
    mkdir("server/uploads", 0755);
}

static std::string uploads_dir() {
    // 优先当前目录 uploads，否则 server/uploads
    struct stat st{};
    if (stat("uploads", &st) == 0 && S_ISDIR(st.st_mode)) return "uploads";
    return "server/uploads";
}

static void broadcast(FrameType type, const std::string& payload, int except_fd = -1) {
    std::vector<int> fds;
    {
        std::lock_guard<std::mutex> lk(g_mu);
        for (auto& kv : g_clients) {
            if (kv.first != except_fd) fds.push_back(kv.first);
        }
    }
    for (int fd : fds) {
        if (!send_frame(fd, type, payload)) {
            log_line("broadcast send fail fd=" + std::to_string(fd));
        }
    }
}

static void send_sys(int fd, const std::string& msg) {
    send_frame(fd, FrameType::SYS, msg);
}

static int find_fd_by_nick(const std::string& nick) {
    std::lock_guard<std::mutex> lk(g_mu);
    for (auto& kv : g_clients) {
        if (kv.second.nick == nick) return kv.first;
    }
    return -1;
}

static std::string list_nicks() {
    std::lock_guard<std::mutex> lk(g_mu);
    std::ostringstream oss;
    bool first = true;
    for (auto& kv : g_clients) {
        if (kv.second.nick.empty()) continue;
        if (!first) oss << ",";
        oss << kv.second.nick;
        first = false;
    }
    return oss.str();
}

static void remove_client(int fd) {
    std::string nick;
    {
        std::lock_guard<std::mutex> lk(g_mu);
        auto it = g_clients.find(fd);
        if (it != g_clients.end()) {
            nick = it->second.nick;
            g_clients.erase(it);
        }
    }
    ::close(fd);
    if (!nick.empty()) {
        log_line("client leave nick=" + nick + " fd=" + std::to_string(fd));
        broadcast(FrameType::SYS, nick + " 已离开聊天室");
    } else {
        log_line("client leave fd=" + std::to_string(fd));
    }
}

// 文件中继：记录进行中的传输（目标为 * 时存盘到服务器）
struct FileXfer {
    std::string sender;
    std::string filename;
    std::string target; // nick 或 "*"
    uint64_t size{0};
    uint64_t received{0};
    int target_fd{-1};
    std::ofstream server_file;
};
static std::map<int, FileXfer> g_xfers; // keyed by sender fd

static void handle_client(int fd) {
    Frame fr;
    while (g_running.load() && recv_frame(fd, fr)) {
        log_line("recv type=" + type_name(fr.type) + " len=" + std::to_string(fr.payload.size())
                 + " fd=" + std::to_string(fd));

        if (fr.type == FrameType::NICK) {
            std::string nick = fr.payload;
            // 去空白
            while (!nick.empty() && (nick.back() == '\n' || nick.back() == '\r' || nick.back() == ' '))
                nick.pop_back();
            if (nick.empty() || nick.size() > 32) {
                send_sys(fd, "昵称非法");
                continue;
            }
            if (nick == "*") {
                send_sys(fd, "昵称不可为 *");
                continue;
            }
            bool dup = false;
            {
                std::lock_guard<std::mutex> lk(g_mu);
                for (auto& kv : g_clients) {
                    if (kv.first != fd && kv.second.nick == nick) { dup = true; break; }
                }
                if (!dup) g_clients[fd].nick = nick;
            }
            if (dup) {
                send_sys(fd, "昵称已被占用: " + nick);
            } else {
                send_sys(fd, "欢迎 " + nick);
                broadcast(FrameType::SYS, nick + " 加入聊天室", fd);
                log_line("nick set fd=" + std::to_string(fd) + " nick=" + nick);
            }
        } else if (fr.type == FrameType::CHAT) {
            std::string from;
            {
                std::lock_guard<std::mutex> lk(g_mu);
                auto it = g_clients.find(fd);
                if (it != g_clients.end()) from = it->second.nick;
            }
            if (from.empty()) {
                send_sys(fd, "请先 /nick 设置昵称");
                continue;
            }
            std::string msg = fr.payload;
            std::string down = from + "\t" + msg;
            broadcast(FrameType::CHAT, down);
            log_line("CHAT from=" + from + " msg=" + msg);
        } else if (fr.type == FrameType::LIST) {
            send_frame(fd, FrameType::LIST, list_nicks());
        } else if (fr.type == FrameType::PING) {
            send_frame(fd, FrameType::PONG, fr.payload);
        } else if (fr.type == FrameType::FILE_META) {
            // sender\tfilename\tsize\ttarget  — 客户端发来时 sender 可空，由服务器填
            std::string from;
            {
                std::lock_guard<std::mutex> lk(g_mu);
                auto it = g_clients.find(fd);
                if (it != g_clients.end()) from = it->second.nick;
            }
            if (from.empty()) {
                send_sys(fd, "请先设置昵称再发文件");
                continue;
            }
            std::istringstream iss(fr.payload);
            std::string a, filename, size_s, target;
            // 允许客户端发: filename\tsize\ttarget  或  sender\tfilename\tsize\ttarget
            std::vector<std::string> parts;
            std::string tok;
            while (std::getline(iss, tok, '\t')) parts.push_back(tok);
            if (parts.size() == 3) {
                filename = parts[0]; size_s = parts[1]; target = parts[2];
            } else if (parts.size() >= 4) {
                filename = parts[1]; size_s = parts[2]; target = parts[3];
            } else {
                send_sys(fd, "FILE_META 格式错误");
                continue;
            }
            uint64_t fsize = 0;
            try { fsize = std::stoull(size_s); } catch (...) {
                send_sys(fd, "文件大小非法");
                continue;
            }
            FileXfer xf;
            xf.sender = from;
            xf.filename = filename;
            xf.target = target.empty() ? "*" : target;
            xf.size = fsize;
            xf.received = 0;

            if (xf.target == "*") {
                // 存到服务器
                std::string path = uploads_dir() + "/" + from + "_" + filename;
                xf.server_file.open(path, std::ios::binary);
                if (!xf.server_file) {
                    send_sys(fd, "服务器无法创建上传文件");
                    continue;
                }
                xf.target_fd = -1;
                send_sys(fd, "开始上传到服务器: " + path);
                log_line("FILE_META upload to server from=" + from + " file=" + filename
                         + " size=" + size_s);
            } else {
                int tfd = find_fd_by_nick(xf.target);
                if (tfd < 0) {
                    send_sys(fd, "目标用户不在线: " + xf.target);
                    continue;
                }
                xf.target_fd = tfd;
                // 转发给目标
                std::string meta = from + "\t" + filename + "\t" + size_s + "\t" + xf.target;
                if (!send_frame(tfd, FrameType::FILE_META, meta)) {
                    send_sys(fd, "转发 FILE_META 失败");
                    continue;
                }
                send_sys(fd, "开始向 " + xf.target + " 发送文件 " + filename);
                log_line("FILE_META relay " + from + " -> " + xf.target + " file=" + filename);
            }
            {
                std::lock_guard<std::mutex> lk(g_mu);
                g_xfers[fd] = std::move(xf);
            }
        } else if (fr.type == FrameType::FILE_CHUNK) {
            FileXfer* px = nullptr;
            {
                std::lock_guard<std::mutex> lk(g_mu);
                auto it = g_xfers.find(fd);
                if (it != g_xfers.end()) px = &it->second;
            }
            if (!px) {
                send_sys(fd, "无进行中的文件传输");
                continue;
            }
            px->received += fr.payload.size();
            if (px->target == "*") {
                px->server_file.write(fr.payload.data(), static_cast<std::streamsize>(fr.payload.size()));
            } else if (px->target_fd >= 0) {
                if (!send_frame(px->target_fd, FrameType::FILE_CHUNK, fr.payload.data(),
                                static_cast<uint32_t>(fr.payload.size()))) {
                    send_sys(fd, "转发 FILE_CHUNK 失败");
                }
            }
            log_line("FILE_CHUNK from=" + px->sender + " +" + std::to_string(fr.payload.size())
                     + " total=" + std::to_string(px->received) + "/" + std::to_string(px->size));
        } else if (fr.type == FrameType::FILE_END) {
            FileXfer xf;
            bool ok = false;
            {
                std::lock_guard<std::mutex> lk(g_mu);
                auto it = g_xfers.find(fd);
                if (it != g_xfers.end()) {
                    xf = std::move(it->second);
                    g_xfers.erase(it);
                    ok = true;
                }
            }
            if (!ok) {
                send_sys(fd, "无进行中的文件传输(END)");
                continue;
            }
            if (xf.target == "*") {
                xf.server_file.close();
                std::string path = uploads_dir() + "/" + xf.sender + "_" + xf.filename;
                send_sys(fd, "上传完成: " + path);
                broadcast(FrameType::SYS, xf.sender + " 上传了文件 " + xf.filename + " 到服务器");
            } else if (xf.target_fd >= 0) {
                std::string endp = xf.sender + "\t" + xf.filename + "\tok\t" + xf.target;
                send_frame(xf.target_fd, FrameType::FILE_END, endp);
                send_sys(fd, "文件已发送给 " + xf.target);
            }
            log_line("FILE_END from=" + xf.sender + " file=" + xf.filename
                     + " received=" + std::to_string(xf.received));
        } else {
            send_sys(fd, "未知帧类型");
        }
    }
    {
        std::lock_guard<std::mutex> lk(g_mu);
        g_xfers.erase(fd);
    }
    remove_client(fd);
}

static void on_signal(int) { g_running = false; }

int main(int argc, char** argv) {
    int port = 9000;
    std::string logpath = "server.log";
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if ((a == "-p" || a == "--port") && i + 1 < argc) {
            port = std::atoi(argv[++i]);
        } else if ((a == "-l" || a == "--log") && i + 1 < argc) {
            logpath = argv[++i];
        } else if (a == "-h" || a == "--help") {
            std::cout << "用法: server [-p port] [-l logfile]\n默认端口 9000\n";
            return 0;
        }
    }

    ensure_uploads();
    g_log.open(logpath, std::ios::app);
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);

    int listen_fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd < 0) {
        perror("socket");
        return 1;
    }
    int yes = 1;
    setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY); // 0.0.0.0
    addr.sin_port = htons(static_cast<uint16_t>(port));

    if (bind(listen_fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        perror("bind");
        return 1;
    }
    if (listen(listen_fd, 64) < 0) {
        perror("listen");
        return 1;
    }

    log_line("server listening 0.0.0.0:" + std::to_string(port));
    log_line("uploads dir=" + uploads_dir());

    // 接受循环：用较短超时以便响应退出信号
    while (g_running.load()) {
        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(listen_fd, &rfds);
        timeval tv{1, 0};
        int sel = select(listen_fd + 1, &rfds, nullptr, nullptr, &tv);
        if (sel < 0) {
            if (errno == EINTR) continue;
            perror("select");
            break;
        }
        if (sel == 0) continue;
        if (!FD_ISSET(listen_fd, &rfds)) continue;

        sockaddr_in cli{};
        socklen_t clen = sizeof(cli);
        int cfd = accept(listen_fd, reinterpret_cast<sockaddr*>(&cli), &clen);
        if (cfd < 0) {
            if (errno == EINTR) continue;
            perror("accept");
            continue;
        }
        char ipbuf[64];
        inet_ntop(AF_INET, &cli.sin_addr, ipbuf, sizeof(ipbuf));
        std::string peer = std::string(ipbuf) + ":" + std::to_string(ntohs(cli.sin_port));
        {
            std::lock_guard<std::mutex> lk(g_mu);
            g_clients[cfd] = Client{cfd, "", peer};
        }
        log_line("accept " + peer + " fd=" + std::to_string(cfd));
        send_sys(cfd, "已连接 CN-Chat 服务器，请用 NICK 帧或客户端 /nick 设置昵称");
        std::thread(handle_client, cfd).detach();
    }

    log_line("server shutting down");
    ::close(listen_fd);
    {
        std::lock_guard<std::mutex> lk(g_mu);
        for (auto& kv : g_clients) ::close(kv.first);
        g_clients.clear();
    }
    return 0;
}
