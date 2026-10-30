// 乙 — TCP 聊天/文件传输客户端（交互式 CLI）
#include <ctime>
// 课程《计算机网络技术》1960193 | 天津理工大学华信软件学院
// 学生占位：乙
#include "../common/protocol.hpp"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>

#include <netdb.h>
#include <netinet/in.h>
#include <sys/stat.h>

using namespace cn;

static std::atomic<bool> g_running{true};
static std::mutex g_io;
static std::ofstream g_log;

static void log_line(const std::string& s) {
    auto now = std::chrono::system_clock::now();
    auto t = std::chrono::system_clock::to_time_t(now);
    char buf[64];
    std::strftime(buf, sizeof(buf), "%F %T", std::localtime(&t));
    std::string line = std::string("[") + buf + "] " + s;
    if (g_log.is_open()) {
        g_log << line << std::endl;
        g_log.flush();
    }
}

static void print_line(const std::string& s) {
    std::lock_guard<std::mutex> lk(g_io);
    std::cout << s << std::endl;
}

// 接收文件时的状态
struct RecvFile {
    bool active{false};
    std::string sender;
    std::string filename;
    uint64_t size{0};
    uint64_t got{0};
    std::ofstream ofs;
};

static RecvFile g_recv;

static void recv_loop(int fd) {
    Frame fr;
    while (g_running.load() && recv_frame(fd, fr)) {
        log_line("recv type=" + type_name(fr.type) + " len=" + std::to_string(fr.payload.size()));
        if (fr.type == FrameType::SYS) {
            print_line("[SYS] " + fr.payload);
        } else if (fr.type == FrameType::CHAT) {
            // from\tmessage
            auto pos = fr.payload.find('\t');
            if (pos == std::string::npos) {
                print_line("[CHAT] " + fr.payload);
            } else {
                print_line("[CHAT] " + fr.payload.substr(0, pos) + ": " + fr.payload.substr(pos + 1));
            }
        } else if (fr.type == FrameType::LIST) {
            print_line("[在线] " + (fr.payload.empty() ? "(无)" : fr.payload));
        } else if (fr.type == FrameType::FILE_META) {
            // sender\tfilename\tsize\ttarget
            std::istringstream iss(fr.payload);
            std::string sender, filename, size_s, target;
            std::getline(iss, sender, '\t');
            std::getline(iss, filename, '\t');
            std::getline(iss, size_s, '\t');
            std::getline(iss, target, '\t');
            uint64_t sz = 0;
            try { sz = std::stoull(size_s); } catch (...) { sz = 0; }
            std::string outpath = "recv_" + sender + "_" + filename;
            g_recv.ofs.open(outpath, std::ios::binary);
            if (!g_recv.ofs) {
                print_line("[文件] 无法创建本地文件: " + outpath);
                continue;
            }
            g_recv.active = true;
            g_recv.sender = sender;
            g_recv.filename = filename;
            g_recv.size = sz;
            g_recv.got = 0;
            print_line("[文件] 开始接收 " + filename + " 来自 " + sender
                       + " 大小=" + size_s + " -> " + outpath);
        } else if (fr.type == FrameType::FILE_CHUNK) {
            if (!g_recv.active) continue;
            g_recv.ofs.write(fr.payload.data(), static_cast<std::streamsize>(fr.payload.size()));
            g_recv.got += fr.payload.size();
            print_line("[文件] 进度 " + std::to_string(g_recv.got) + "/" + std::to_string(g_recv.size));
        } else if (fr.type == FrameType::FILE_END) {
            if (g_recv.active) {
                g_recv.ofs.close();
                g_recv.active = false;
                print_line("[文件] 接收完成: recv_" + g_recv.sender + "_" + g_recv.filename);
            } else {
                print_line("[文件] END: " + fr.payload);
            }
        } else if (fr.type == FrameType::PONG) {
            print_line("[PONG]");
        }
    }
    g_running = false;
    print_line("[连接已断开]");
}

static bool send_file(int fd, const std::string& path, const std::string& target) {
    std::ifstream ifs(path, std::ios::binary);
    if (!ifs) {
        print_line("无法打开文件: " + path);
        return false;
    }
    ifs.seekg(0, std::ios::end);
    auto sz = ifs.tellg();
    ifs.seekg(0, std::ios::beg);
    if (sz < 0) {
        print_line("无法获取文件大小");
        return false;
    }
    // 取 basename
    std::string filename = path;
    auto slash = filename.find_last_of('/');
    if (slash != std::string::npos) filename = filename.substr(slash + 1);

    std::string meta = filename + "\t" + std::to_string(static_cast<uint64_t>(sz)) + "\t" + target;
    if (!send_frame(fd, FrameType::FILE_META, meta)) {
        print_line("发送 FILE_META 失败");
        return false;
    }
    log_line("send FILE_META " + meta);

    const size_t CHUNK = 32 * 1024;
    std::vector<char> buf(CHUNK);
    uint64_t sent = 0;
    while (ifs) {
        ifs.read(buf.data(), static_cast<std::streamsize>(CHUNK));
        std::streamsize n = ifs.gcount();
        if (n <= 0) break;
        if (!send_frame(fd, FrameType::FILE_CHUNK, buf.data(), static_cast<uint32_t>(n))) {
            print_line("发送 FILE_CHUNK 失败");
            return false;
        }
        sent += static_cast<uint64_t>(n);
        print_line("[发送] " + std::to_string(sent) + "/" + std::to_string(static_cast<uint64_t>(sz)));
    }
    std::string endp = "ok";
    if (!send_frame(fd, FrameType::FILE_END, endp)) {
        print_line("发送 FILE_END 失败");
        return false;
    }
    log_line("send FILE_END file=" + filename);
    print_line("[发送] 完成: " + filename + " -> " + target);
    return true;
}

static void print_help() {
    print_line("命令:");
    print_line("  /nick <名字>              设置昵称");
    print_line("  /say <消息>               发送聊天（也可直接输入消息）");
    print_line("  /list                     查看在线用户");
    print_line("  /sendfile <路径> [目标]   发文件；目标省略或 * 表示上传到服务器");
    print_line("  /ping                     心跳");
    print_line("  /help                     帮助");
    print_line("  /quit                     退出");
}

int main(int argc, char** argv) {
    std::string host = "127.0.0.1";
    int port = 9000;
    std::string logpath = "client.log";
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if ((a == "-h" || a == "--host") && i + 1 < argc) host = argv[++i];
        else if ((a == "-p" || a == "--port") && i + 1 < argc) port = std::atoi(argv[++i]);
        else if ((a == "-l" || a == "--log") && i + 1 < argc) logpath = argv[++i];
        else if (a == "--help") {
            std::cout << "用法: client [-h host] [-p port] [-l logfile]\n";
            return 0;
        }
    }

    g_log.open(logpath, std::ios::app);

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    addrinfo* res = nullptr;
    std::string port_s = std::to_string(port);
    int gai = getaddrinfo(host.c_str(), port_s.c_str(), &hints, &res);
    if (gai != 0) {
        std::cerr << "getaddrinfo: " << gai_strerror(gai) << std::endl;
        return 1;
    }
    int fd = -1;
    for (addrinfo* p = res; p; p = p->ai_next) {
        fd = ::socket(p->ai_family, p->ai_socktype, p->ai_protocol);
        if (fd < 0) continue;
        if (connect(fd, p->ai_addr, p->ai_addrlen) == 0) break;
        ::close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (fd < 0) {
        std::cerr << "连接失败 " << host << ":" << port << std::endl;
        return 1;
    }

    print_line("已连接 " + host + ":" + std::to_string(port));
    log_line("connected " + host + ":" + std::to_string(port));
    print_help();

    std::thread thr(recv_loop, fd);

    std::string line;
    while (g_running.load()) {
        {
            std::lock_guard<std::mutex> lk(g_io);
            std::cout << "> " << std::flush;
        }
        if (!std::getline(std::cin, line)) {
            g_running = false;
            break;
        }
        if (!g_running.load()) break;

        if (line.empty()) continue;

        if (line == "/quit" || line == "/exit") {
            g_running = false;
            break;
        } else if (line == "/help") {
            print_help();
        } else if (line.rfind("/nick ", 0) == 0) {
            std::string nick = line.substr(6);
            while (!nick.empty() && nick.front() == ' ') nick.erase(nick.begin());
            if (!send_frame(fd, FrameType::NICK, nick)) {
                print_line("发送失败");
                break;
            }
            log_line("send NICK " + nick);
        } else if (line.rfind("/say ", 0) == 0) {
            std::string msg = line.substr(5);
            if (!send_frame(fd, FrameType::CHAT, msg)) {
                print_line("发送失败");
                break;
            }
            log_line("send CHAT " + msg);
        } else if (line == "/list") {
            send_frame(fd, FrameType::LIST, "");
        } else if (line == "/ping") {
            send_frame(fd, FrameType::PING, "ping");
        } else if (line.rfind("/sendfile ", 0) == 0) {
            std::istringstream iss(line.substr(10));
            std::string path, target;
            iss >> path;
            if (!(iss >> target)) target = "*";
            send_file(fd, path, target);
        } else if (line[0] == '/') {
            print_line("未知命令，输入 /help");
        } else {
            // 直接当聊天
            if (!send_frame(fd, FrameType::CHAT, line)) {
                print_line("发送失败");
                break;
            }
            log_line("send CHAT " + line);
        }
    }

    ::shutdown(fd, SHUT_RDWR);
    ::close(fd);
    if (thr.joinable()) thr.join();
    print_line("客户端退出");
    return 0;
}
