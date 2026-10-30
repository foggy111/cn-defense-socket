#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
丁 — LLM 辅助日志/协议诊断模块
课程《计算机网络技术》1960193 | 天津理工大学华信软件学院

用法:
  python3 diagnose.py ../samples/sample_chat_log.txt
  python3 diagnose.py ../results/smoke_server.log --mock
  OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.openai.com/v1 \\
    python3 diagnose.py some.log

环境变量（OpenAI 兼容）:
  OPENAI_API_KEY   — API 密钥；缺失则自动进入 mock 模式
  OPENAI_BASE_URL  — 可选，默认 https://api.openai.com/v1
  OPENAI_MODEL     — 可选，默认 gpt-4o-mini
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Tuple


SYSTEM_PROMPT = """你是一名计算机网络课程助教，擅长 TCP Socket、应用层自定义协议与日志排查。
请根据学生提供的服务器/客户端日志，用中文输出结构化诊断：
1) 现象摘要
2) 可能涉及的 TCP/协议问题（连接、半包粘包、帧解析、昵称冲突、文件中继等）
3) 与本项目协议（magic=CN, length-prefixed, CHAT/FILE_* /SYS）的对应关系
4) 建议的排查与修复步骤
5) 答辩时可讲解的知识点（三次握手、可靠传输、字节序、并发模型）
保持专业、具体，避免空话。"""


def build_user_prompt(log_text: str, path: str) -> str:
    return (
        f"以下是项目日志文件 `{path}` 的内容（可能截断）。\n"
        f"项目协议：帧头 magic='CN' + version + type + uint32_be length + payload；"
        f"类型含 SYS/CHAT/NICK/FILE_META/FILE_CHUNK/FILE_END/LIST。\n"
        f"服务器默认 0.0.0.0:9000，支持多客户端广播与文件中继/上传。\n\n"
        f"---- 日志开始 ----\n{log_text}\n---- 日志结束 ----\n\n"
        f"请给出诊断报告。"
    )


def heuristic_findings(log_text: str) -> List[str]:
    """无 API 时的规则引擎（mock），演示 LLM 集成点。"""
    findings: List[str] = []
    lines = log_text.splitlines()

    if any("listening" in ln for ln in lines):
        findings.append("检测到服务器成功 bind/listen，TCP 被动打开完成，进入并发 accept 阶段。")
    if any("accept" in ln for ln in lines):
        findings.append("存在客户端三次握手成功后的 accept 记录，说明传输层连接已建立。")
    if any("nick set" in ln.lower() or "NICK" in ln for ln in lines):
        findings.append("出现昵称注册（NICK），应用层会话身份已绑定到 TCP 连接（fd）。")
    if any("CHAT" in ln for ln in lines):
        findings.append("出现 CHAT 帧，对应应用层广播：服务器读入后向其他已连接 socket 写出。")
    if any("FILE_META" in ln for ln in lines):
        findings.append("出现 FILE_META：文件传输控制面启动，随后应有 FILE_CHUNK / FILE_END。")
    if any("FILE_CHUNK" in ln for ln in lines):
        findings.append("出现 FILE_CHUNK：注意粘包/半包由 length-prefixed 帧边界解决，而非依赖 TCP 消息边界。")
    if any("fail" in ln.lower() or "错误" in ln or "非法" in ln for ln in lines):
        findings.append("日志含失败/非法提示，需核对帧 magic/version、payload 长度与业务字段分隔符（\\t）。")
    if any("leave" in ln or "断开" in ln for ln in lines):
        findings.append("存在连接关闭：检查是否为对端 close、进程退出或中间设备 RST。")

    # 简单时序检查：FILE_CHUNK 前应有 FILE_META
    saw_meta = False
    for ln in lines:
        if "FILE_META" in ln:
            saw_meta = True
        if "FILE_CHUNK" in ln and not saw_meta:
            findings.append("警告：在未见 FILE_META 的情况下出现 FILE_CHUNK，可能是日志截断或协议状态机异常。")
            break

    if not findings:
        findings.append("未匹配到典型关键字；请确认日志来自本项目 server/client，或补充更多运行轨迹。")
    return findings


def mock_diagnose(log_text: str, path: str) -> str:
    findings = heuristic_findings(log_text)
    bullets = "\n".join(f"- {f}" for f in findings)
    return f"""【Mock 模式诊断报告】（未配置 OPENAI_API_KEY，或指定 --mock）
日志文件: {path}
日志行数: {len(log_text.splitlines())}

## 1) 现象摘要
基于规则引擎对日志关键字的匹配结果如下。此模式用于答辩演示与离线验收，
真实部署时可配置 OpenAI 兼容 API 获得自然语言深度分析。

## 2) 可能的 TCP/协议问题与观察
{bullets}

## 3) 与本项目协议的对应
- 帧格式: magic(CN) | version(1) | type(u8) | length(u32 BE) | payload
- CHAT 广播依赖服务器维护的 fd→nick 映射表
- 文件: FILE_META → 多个 FILE_CHUNK → FILE_END；目标为 * 时落盘 server/uploads/
- length-prefixed 用于在字节流上恢复消息边界（解决 TCP 粘包/半包）

## 4) 建议排查步骤
1. 确认服务器日志有 `listening 0.0.0.0:9000`
2. 客户端先 `/nick` 再聊天或发文件
3. 对照 PROTOCOL.md 检查载荷字段顺序与分隔符
4. 用 `ss -lntp | grep 9000` 确认监听；用抓包观察帧头 magic
5. 大文件传输时关注 CHUNK 大小与磁盘权限（uploads/）

## 5) 答辩知识点提示
- TCP 三次握手 / 四次挥手与 socket API（socket/bind/listen/accept/connect）映射
- 字节序：htonl/ntohl 保证跨主机 length 一致
- 并发：thread-per-client + mutex 保护共享客户端表
- 应用层协议设计：类型枚举、版本号、最大帧长防 DoS

（若设置 OPENAI_API_KEY，可去掉 --mock 获得大模型完整分析。）
"""


def call_openai_compatible(system: str, user: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 未设置")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    url = f"{base}/chat/completions"
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e}") from e

    obj = json.loads(raw)
    try:
        return obj["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"响应格式异常: {raw[:500]}") from e


def read_log(path: Path, max_chars: int = 24000) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[: max_chars // 2] + "\n\n...[中间截断]...\n\n" + text[-max_chars // 2 :]
    return text


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM 辅助 TCP/协议日志诊断（丁）")
    parser.add_argument("logfile", help="服务器或客户端日志路径")
    parser.add_argument("--mock", action="store_true", help="强制离线 mock 模式")
    parser.add_argument("-o", "--output", help="将诊断写入文件")
    args = parser.parse_args(argv)

    path = Path(args.logfile)
    if not path.is_file():
        print(f"文件不存在: {path}", file=sys.stderr)
        return 1

    log_text = read_log(path)
    use_mock = args.mock or not os.environ.get("OPENAI_API_KEY", "").strip()

    if use_mock:
        report = mock_diagnose(log_text, str(path))
        mode = "mock"
    else:
        try:
            report = call_openai_compatible(
                SYSTEM_PROMPT, build_user_prompt(log_text, str(path))
            )
            mode = "api"
        except Exception as exc:  # noqa: BLE001 — 答辩演示需友好降级
            print(f"[警告] API 调用失败，降级 mock: {exc}", file=sys.stderr)
            report = mock_diagnose(log_text, str(path))
            mode = "mock-fallback"

    header = f"=== diagnose mode={mode} file={path} ===\n"
    full = header + report + "\n"
    print(full)
    if args.output:
        Path(args.output).write_text(full, encoding="utf-8")
        print(f"[已写入] {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
