#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate four TJUT CN course-design defense Word reports."""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

ROOT = Path('/workspace/cn-defense-socket')
OUT = ROOT / 'docs' / 'reports'
ASCII_OUT = OUT / 'ascii'
SHOT = ROOT / 'results' / 'screenshots'
BLURBS = json.loads((ROOT / 'scripts' / 'report_blurbs.json').read_text(encoding='utf-8'))
OUT.mkdir(parents=True, exist_ok=True)
ASCII_OUT.mkdir(parents=True, exist_ok=True)


def read(p: str) -> str:
    return (ROOT / p).read_text(encoding='utf-8', errors='replace')


def set_run_font(run, cn='宋体', en='Times New Roman', size=12, bold=False, code=False):
    if code:
        cn = en = 'Consolas'
        size = size or 8
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = en
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    rFonts.set(qn('w:ascii'), en)
    rFonts.set(qn('w:hAnsi'), en)
    rFonts.set(qn('w:eastAsia'), cn)
    rFonts.set(qn('w:cs'), en)


def add_page_number(section):
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run('第 ')
    set_run_font(run, size=9)
    fld1 = OxmlElement('w:fldChar')
    fld1.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = 'PAGE'
    fld2 = OxmlElement('w:fldChar')
    fld2.set(qn('w:fldCharType'), 'end')
    run2 = p.add_run()
    run2._element.append(fld1)
    run2._element.append(instr)
    run2._element.append(fld2)
    set_run_font(run2, size=9)
    run3 = p.add_run(' 页')
    set_run_font(run3, size=9)


def setup_doc(doc: Document):
    for sec in doc.sections:
        sec.page_width = Cm(21.0)
        sec.page_height = Cm(29.7)
        sec.left_margin = Cm(2.5)
        sec.right_margin = Cm(2.5)
        sec.top_margin = Cm(2.5)
        sec.bottom_margin = Cm(2.5)
        add_page_number(sec)
        header = sec.header
        header.is_linked_to_previous = False
        hp = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        hr = hp.add_run('计算机网络技术课程设计答辩报告')
        set_run_font(hr, size=9, cn='宋体')
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)
    style._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    pf = style.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.space_after = Pt(6)


def p_text(doc, text, *, size=12, bold=False, center=False, first_indent=True,
           space_after=6, cn='宋体'):
    para = doc.add_paragraph()
    if center:
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if first_indent and not center:
        para.paragraph_format.first_line_indent = Cm(0.74)
    para.paragraph_format.space_after = Pt(space_after)
    para.paragraph_format.line_spacing = 1.5
    run = para.add_run(text)
    set_run_font(run, size=size, bold=bold, cn=cn)
    return para


def heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        set_run_font(
            run,
            size=16 if level == 1 else 14 if level == 2 else 12,
            bold=True,
            cn='黑体',
        )
    return h


def set_cell_shading(cell, fill='F2F2F2'):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn('w:shd')):
        tcPr.remove(old)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill)
    tcPr.append(shd)


def set_cell_borders(cell, color='BFBFBF', sz='4'):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn('w:tcBorders')):
        tcPr.remove(old)
    borders = OxmlElement('w:tcBorders')
    for edge in ('top', 'left', 'bottom', 'right'):
        el = OxmlElement(f'w:{edge}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), sz)
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), color)
        borders.append(el)
    tcPr.append(borders)


def add_code_block(doc, code: str, lines_per_block: int = 45):
    """Place source in shaded single-column tables; no markdown fences."""
    text = code.replace('\r\n', '\n').replace('\t', '    ').rstrip() + '\n'
    # Strip accidental markdown fences if any slipped in
    text = re.sub(r'^```[a-zA-Z0-9_+-]*\n?', '', text, flags=re.M)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.M)
    lines = text.split('\n')
    # Drop trailing empty from split
    if lines and lines[-1] == '':
        lines = lines[:-1]
    if not lines:
        return
    for start in range(0, len(lines), lines_per_block):
        chunk = lines[start:start + lines_per_block]
        table = doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = True
        cell = table.rows[0].cells[0]
        set_cell_shading(cell, 'F2F2F2')
        set_cell_borders(cell)
        # Clear default empty para and write line-by-line for wrapping
        cell.text = ''
        first = True
        for line in chunk:
            if first:
                para = cell.paragraphs[0]
                first = False
            else:
                para = cell.add_paragraph()
            para.paragraph_format.space_before = Pt(0)
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.line_spacing = 1.0
            para.paragraph_format.first_line_indent = Cm(0)
            run = para.add_run(line if line else ' ')
            set_run_font(run, size=8, code=True)
            run.font.color.rgb = RGBColor(0x20, 0x20, 0x20)
        # Spacer after each block
        sp = doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(4)
        sp.paragraph_format.space_before = Pt(0)


def split_code_sections(code: str, kind: str) -> list[tuple[str, str]]:
    """Break long sources into labeled subsections for appendix."""
    lines = code.replace('\r\n', '\n').split('\n')
    n = len(lines)

    def join(a, b):
        return '\n'.join(lines[a:b])

    if kind == 'protocol':
        return [
            ('头文件与帧类型定义', join(0, 40)),
            ('可靠收发原语 send_all / recv_all', join(40, 90)),
            ('组帧与解帧 send_frame / recv_frame', join(90, n)),
        ]
    if kind == 'server':
        # Find landmarks (actual symbol: handle_client)
        idx_handler = next(
            (i for i, ln in enumerate(lines) if 'handle_client' in ln and '{' in ln),
            120,
        )
        idx_main = next(
            (i for i, ln in enumerate(lines) if re.match(r'^int\s+main\s*\(', ln)),
            max(n - 80, idx_handler + 1),
        )
        return [
            ('头文件、全局状态与日志辅助', join(0, 80)),
            ('广播、会话清理与文件辅助', join(80, idx_handler)),
            ('客户端处理线程 handle_client', join(idx_handler, idx_main)),
            ('主函数：监听、accept 与退出', join(idx_main, n)),
        ]
    if kind == 'client':
        idx_recv = next((i for i, ln in enumerate(lines) if 'void recv_loop' in ln), 58)
        idx_sendfile = next((i for i, ln in enumerate(lines) if 'send_file' in ln and '{' in ln), 120)
        idx_main = next((i for i, ln in enumerate(lines) if re.match(r'^int\s+main\s*\(', ln)), max(n - 90, 150))
        return [
            ('头文件、日志与接收状态', join(0, idx_recv)),
            ('接收线程 recv_loop', join(idx_recv, idx_sendfile)),
            ('文件发送与命令解析', join(idx_sendfile, idx_main)),
            ('主函数：连接与交互循环', join(idx_main, n)),
        ]
    if kind == 'llm':
        idx_heur = next((i for i, ln in enumerate(lines) if 'def heuristic_findings' in ln), 50)
        idx_mock = next((i for i, ln in enumerate(lines) if 'def mock_diagnose' in ln or 'def call_openai' in ln), 100)
        idx_main = next((i for i, ln in enumerate(lines) if 'def main' in ln), max(n - 60, 140))
        return [
            ('模块说明与提示词', join(0, idx_heur)),
            ('规则引擎 heuristic_findings', join(idx_heur, idx_mock)),
            ('Mock / API 调用与输出', join(idx_mock, idx_main)),
            ('命令行入口 main', join(idx_main, n)),
        ]
    if kind == 'protocol_md':
        mid = n // 2
        return [('协议概述与帧格式', join(0, mid)), ('交互流程与约束', join(mid, n))]
    if kind == 'design':
        # Split design doc into ~4 chunks by heading lines
        heads = [i for i, ln in enumerate(lines) if ln.startswith('#')]
        if len(heads) >= 4:
            cuts = [0] + heads[1:4] + [n]
            labels = ['选题与需求', '总体设计', '详细设计与协议', '测试与总结']
            parts = []
            for i in range(4):
                parts.append((labels[i], join(cuts[i], cuts[i + 1])))
            return parts
        step = max(n // 4, 1)
        return [
            ('第一部分', join(0, step)),
            ('第二部分', join(step, 2 * step)),
            ('第三部分', join(2 * step, 3 * step)),
            ('第四部分', join(3 * step, n)),
        ]
    # generic halves / thirds
    if n <= 80:
        return [('全文', code)]
    if n <= 160:
        mid = n // 2
        return [('前半部分', join(0, mid)), ('后半部分', join(mid, n))]
    step = n // 3
    return [
        ('第 1 节', join(0, step)),
        ('第 2 节', join(step, 2 * step)),
        ('第 3 节', join(2 * step, n)),
    ]


def add_appendix_file(doc, a_id: str, filename: str, intro: str, code: str, kind: str):
    heading(doc, f'{a_id} {filename}', 2)
    p_text(doc, intro)
    sections = split_code_sections(code, kind)
    if len(sections) == 1:
        add_code_block(doc, sections[0][1])
        return
    for i, (label, body) in enumerate(sections, 1):
        heading(doc, f'{a_id}.{i} {label}', 3)
        p_text(doc, f'本节给出 {filename} 中「{label}」对应源码。')
        add_code_block(doc, body)


def add_figure(doc, name: str, caption: str, prose: str, width=5.8):
    """Prose, then image, then centered 小五 caption."""
    p_text(doc, prose)
    path = SHOT / name
    if path.exists():
        doc.add_picture(str(path), width=Inches(width))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.paragraphs[-1].paragraph_format.space_after = Pt(2)
    else:
        p_text(doc, f'（插图文件缺失：{name}）', center=True, first_indent=False, size=10)
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(2)
    cap.paragraph_format.space_after = Pt(10)
    cap.paragraph_format.first_line_indent = Cm(0)
    run = cap.add_run(caption)
    set_run_font(run, size=10, cn='宋体')  # 小五≈9pt; 10pt per brief


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ''
        run = cell.paragraphs[0].add_run(h)
        set_run_font(run, size=10, bold=True, cn='宋体')
    for r_i, row in enumerate(rows):
        for c_i, val in enumerate(row):
            cell = table.rows[r_i + 1].cells[c_i]
            cell.text = ''
            run = cell.paragraphs[0].add_run(str(val))
            set_run_font(run, size=10, cn='宋体')
    doc.add_paragraph()


def cover(doc, role, name, sid, focus):
    for _ in range(2):
        doc.add_paragraph()
    p_text(doc, '天津理工大学 华信软件学院', size=16, bold=True, center=True,
           first_indent=False, cn='黑体')
    p_text(doc, '《计算机网络技术》课程设计答辩报告', size=18, bold=True, center=True,
           first_indent=False, cn='黑体')
    p_text(doc, '课程代码：1960193', size=14, center=True, first_indent=False)
    doc.add_paragraph()
    p_text(doc, '题目：基于 C++ TCP Socket 的多客户端聊天与文件传输系统', size=14,
           center=True, first_indent=False)
    p_text(doc, '（集成大语言模型 LLM 日志/协议辅助诊断）', size=14, center=True,
           first_indent=False)
    doc.add_paragraph()
    p_text(doc, f'答辩角色：{role}', size=14, center=True, first_indent=False)
    p_text(doc, f'本人负责：{focus}', size=12, center=True, first_indent=False)
    doc.add_paragraph()
    p_text(doc, f'姓    名：{name}', size=14, center=True, first_indent=False)
    p_text(doc, f'学    号：{sid}', size=14, center=True, first_indent=False)
    p_text(doc, '指导教师：____________________', size=14, center=True, first_indent=False)
    p_text(doc, '日    期：2026 年 10 月', size=14, center=True, first_indent=False)
    doc.add_page_break()


def toc_page(doc, entries: list[str]):
    """目录单独成页：进入时已在封面后的新页；写完后再分页。"""
    h = doc.add_heading('目  录', level=1)
    for run in h.runs:
        set_run_font(run, size=16, bold=True, cn='黑体')
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for line in entries:
        p_text(doc, line, first_indent=False, space_after=8)
    doc.add_page_break()


PROTO = read('common/protocol.hpp')
SERVER = read('server/server.cpp')
CLIENT = read('client/client.cpp')
LLM = read('llm/diagnose.py')
PROTOCOL_MD = read('protocol/PROTOCOL.md')
DESIGN = read('docs/02_设计说明书.md')
TOPIC = read('docs/01_选题说明.md')
DIV = read('docs/03_分工与进度.md')
SPEECH = read('docs/04_答辩陈述提纲.md')
SMOKE_LOG = read('results/smoke_server.log')
SMOKE_DIAG = read('results/smoke_diagnose.txt')
README = read('README.md')
PRINCIPLES = BLURBS['principles']
ARCH = BLURBS['arch']
ISSUES = BLURBS['issues']
MAKE_SERVER = read('server/Makefile')
MAKE_CLIENT = read('client/Makefile')
REQS = read('llm/requirements.txt')
DEMO_SH = read('scripts/demo.sh')
SAMPLE_LOG = read('samples/sample_chat_log.txt')

TESTS = [
    ('T1', '单客户端登录', '启动 server；client /nick Alice', '收到欢迎 SYS', '通过'),
    ('T2', '昵称冲突', '两客户端使用同名', '第二人收到错误提示', '通过'),
    ('T3', '双人群聊', 'Alice /say hello', 'Bob 侧显示 CHAT', '通过'),
    ('T4', '在线列表', '/list', '返回逗号分隔昵称', '通过'),
    ('T5', '上传文件', '/sendfile demo.txt *', 'uploads 目录出现文件', '通过'),
    ('T6', '点对点文件', '/sendfile demo.txt Bob', 'Bob 侧生成 recv 文件', '通过'),
    ('T7', '心跳', '/ping', '收到 PONG 或 SYS', '通过'),
    ('T8', '断线清理', '客户端 /quit', '日志记录 leave', '通过'),
    ('T9', '端口占用', '重复 bind 9000', '改用 -p 9001', '已记录'),
    ('T10', 'LLM mock', 'diagnose.py --mock', '输出五段中文诊断', '通过'),
    ('T11', '冒烟脚本', 'bash scripts/demo.sh', '出现 SMOKE_CHAT_OK', '通过'),
    ('T12', '非法帧', 'magic 非 CN', '断开或忽略', '设计覆盖'),
]

REFS = [
    'W. Richard Stevens,《UNIX 网络编程 卷 1》',
    '谢希仁,《计算机网络》（第 8 版）',
    'RFC 793 Transmission Control Protocol',
    'POSIX socket API 手册页（socket、bind、listen、accept、recv、send）',
    '本课程设计仓库 README 与 protocol/PROTOCOL.md',
    'OpenAI Chat Completions API 参考文档',
    '汤子瀛等,《计算机操作系统》并发与互斥相关章节',
]

DEMO_CMD = (
    'cd /mnt/c/Users/niu/OS/cn-defense-socket\n'
    'bash scripts/build.sh\n'
    'cd server && ./server -p 9000 -l ../results/demo_server.log\n'
    'cd client && ./client -h 127.0.0.1 -p 9000\n'
    '# 客户端内：/nick Alice   /say hello   /sendfile ../samples/demo.txt *\n'
    'python3 llm/diagnose.py results/smoke_server.log --mock -o results/smoke_diagnose.txt\n'
)

TOC_COMMON = [
    '摘要',
    '第1章 选题背景与课程要求',
    '第2章 相关网络原理',
    '第3章 系统总体架构与分工',
]


def common_ch123(doc, role_extra: str):
    heading(doc, '第1章 选题背景与课程要求', 1)
    heading(doc, '1.1 选题背景', 2)
    p_text(
        doc,
        '《计算机网络技术》强调理论联系实际。TCP/IP 与 Socket 编程是后续分布式系统、'
        'Web 服务等课程的基础。本组在经典聊天室课题上增加自定义二进制帧协议、文件分块传输，'
        '以及大语言模型对运行日志的辅助诊断，以便同时满足“与网络相关、有真实代码、使用 LLM、'
        '具备一定深度、四人分工清晰”等课程约束。',
    )
    p_text(doc, role_extra)
    heading(doc, '1.2 与课程要求的对应', 2)
    add_table(doc, ['课程要求', '本项目落实'], [
        ['与计算机网络相关', 'TCP Socket、应用层协议、并发连接、网络字节序'],
        ['软件工程真实代码', 'C++17 服务端/客户端 + Python LLM，可编译运行'],
        ['使用大语言模型', 'llm/diagnose.py，无密钥时提供 mock 规则引擎'],
        ['难度与深度', '帧协议、文件中继、多线程、设计说明书'],
        ['四人分工', '甲服务器、乙客户端、丙文档、丁 LLM'],
    ])
    heading(doc, '1.3 本人在选题中的定位', 2)
    p_text(
        doc,
        '四人并行开发的前提是先冻结应用层协议。公共头文件 common/protocol.hpp 规定帧布局与'
        '收发原语，甲、乙据此实现双端；丙维护 PROTOCOL.md 与设计说明书；丁基于日志字段编写'
        '诊断提示词。接口先行、实现并行，是本组在有限学时内完成联调的基本做法。',
    )
    heading(doc, '第2章 相关网络原理', 1)
    for para in PRINCIPLES.split('\n\n'):
        para = para.strip()
        if para:
            p_text(doc, para)
    heading(doc, '2.1 Socket API 与三次握手映射', 2)
    add_table(doc, ['动作', '服务器', '客户端'], [
        ['创建套接字', 'socket(AF_INET, SOCK_STREAM, 0)', '同左'],
        ['绑定', 'bind(0.0.0.0:9000)', '通常不主动 bind'],
        ['被动打开', 'listen', '—'],
        ['接受 / 连接', 'accept', 'connect'],
        ['收发', 'recv / send', 'recv / send'],
        ['关闭', 'close', 'close'],
    ])
    heading(doc, '2.2 粘包、半包与本项目对策', 2)
    p_text(
        doc,
        '对策是固定头加 length 字段：先 recv_all(8) 取得头部，再对 length 做 ntohl，'
        '随后 recv_all(length) 收齐载荷。send_all / recv_all 以循环处理短写、短读与 EINTR。'
        'MAX_PAYLOAD 限制单帧大小，降低恶意超大 length 带来的风险。该机制是答辩时应能独立讲清的重点。',
    )
    heading(doc, '2.3 并发与同步', 2)
    p_text(
        doc,
        'thread-per-client 实现直观，适合课堂演示规模。共享的 fd→nick 表在增删与遍历时必须加互斥锁，'
        '否则广播时可能出现迭代失效或重复释放。accept 循环可配合 select 超时，以便响应退出信号。',
    )
    heading(doc, '第3章 系统总体架构与分工', 1)
    p_text(doc, ARCH)
    add_table(doc, ['角色', '职责', '主要目录'], [
        ['甲', 'TCP 多客户端服务器', 'server/、common/protocol.hpp'],
        ['乙', '交互式客户端', 'client/'],
        ['丙', '选题与设计说明书、协议文档', 'docs/、protocol/'],
        ['丁', 'LLM 诊断与答辩提纲', 'llm/、docs/04_*.md'],
    ])
    heading(doc, '3.1 帧类型一览', 2)
    add_table(doc, ['类型', '值', '含义'], [
        ['SYS', '1', '系统提示 / 错误'],
        ['CHAT', '2', '聊天'],
        ['NICK', '3', '昵称登录'],
        ['FILE_META', '4', '文件元信息'],
        ['FILE_CHUNK', '5', '文件分块'],
        ['FILE_END', '6', '文件结束'],
        ['LIST', '7', '在线列表'],
        ['PING / PONG', '8 / 9', '心跳'],
    ])


def chapter_run_test(doc, figures: list[tuple[str, str, str]]):
    """figures: (filename, caption, prose)"""
    heading(doc, '第6章 编译运行与测试', 1)
    heading(doc, '6.1 环境与编译', 2)
    p_text(
        doc,
        '实验环境为 Windows 下的 WSL（Ubuntu），编译器为支持 C++17 的 g++，并依赖 make 与 python3。'
        '推荐将仓库置于 /mnt/c/Users/niu/OS/cn-defense-socket。一键编译命令为 bash scripts/build.sh。',
    )
    add_figure(
        doc,
        '01_build.png',
        '图6-1 编译与链接成功',
        '图6-1 给出 make / g++ 编译链接通过后的终端输出，说明服务端与客户端目标文件已正确生成。',
    )
    for name, cap, prose in figures:
        add_figure(doc, name, cap, prose)
    heading(doc, '6.2 冒烟日志摘录', 2)
    p_text(doc, '下列为冒烟运行时服务器侧关键日志片段，可与截图对照。')
    add_code_block(doc, SMOKE_LOG)
    heading(doc, '6.3 测试用例表', 2)
    p_text(doc, '表中汇总了联调阶段执行的主要功能与异常用例及结果。')
    add_table(doc, ['编号', '用例', '步骤', '期望', '结果'], TESTS)
    heading(doc, '6.4 手工演示命令', 2)
    p_text(doc, '答辩现场若不用一键脚本，可按下列顺序手工启动服务端、客户端与诊断工具。')
    add_code_block(doc, DEMO_CMD)


def chapter_issues_summary(doc, personal_summary: str):
    heading(doc, '第7章 联调问题与解决', 1)
    for para in ISSUES.split('\n\n'):
        para = para.strip()
        if para:
            p_text(doc, para)
    heading(doc, '第8章 个人总结与展望', 1)
    p_text(doc, personal_summary)
    p_text(
        doc,
        '当前实现尚未引入 TLS 与身份鉴权，界面仍为命令行，文件传输也不支持断点续传。'
        '后续可在加密通道、Web 前端、协议模糊测试以及更细的性能指标方面继续完善。',
    )
    heading(doc, '参考文献', 1)
    for i, r in enumerate(REFS, 1):
        p_text(doc, f'[{i}] {r}', first_indent=False)


def build_jia():
    doc = Document()
    setup_doc(doc)
    cover(doc, '甲（服务器）', '牛昭凯', '20241921', 'TCP 多客户端服务器与协议实现协作')
    toc_page(doc, TOC_COMMON + [
        '第4章 服务器详细设计（本人）',
        '第5章 关键实现说明',
        '第6章 编译运行与测试',
        '第7章 联调问题与解决',
        '第8章 个人总结与展望',
        '参考文献',
        '附录A 完整源码',
    ])
    heading(doc, '摘要', 1)
    p_text(doc, BLURBS['jia_abs'])
    p_text(doc, '关键词：TCP；Socket；多线程；应用层协议；文件传输', first_indent=False)

    common_ch123(
        doc,
        '作为甲，本人将上述原理落实为可运行的 server.cpp：把三次握手完成后的连接纳入会话表，'
        '把字节流还原为帧，再按类型执行业务逻辑，并向日志输出关键事件供丁侧诊断使用。',
    )

    heading(doc, '第4章 服务器详细设计（本人）', 1)
    for title, body in [
        ('4.1 模块结构',
         '服务器以单文件 server.cpp 组织，依赖 common/protocol.hpp。主要流程包括：解析 -p/-l 参数；'
         '创建监听套接字并设置 SO_REUSEADDR；循环 accept；为每个客户端启动线程；在线程中 recv_frame '
         '并按类型分发；用 mutex 保护客户端映射；将关键事件写入 -l 指定日志文件。'),
        ('4.2 监听与连接管理',
         '默认绑定 0.0.0.0:9000，便于局域网其它主机接入。SO_REUSEADDR 可缩短重启后的地址占用等待。'
         'accept 成功后记录对端地址与 fd，并发送 SYS 提示用户先执行 /nick。'),
        ('4.3 昵称、广播与列表',
         'NICK 载荷为昵称字符串，需校验非空且未被占用。CHAT 上行可为纯消息文本，由服务器补全 from '
         '后广播给其它已登录连接。LIST 下行以逗号拼接昵称。广播时在持锁状态下复制 fd 列表，解锁后再 '
         'send，以缩短临界区。'),
        ('4.4 文件上传与中继',
         'FILE_META 解析 sender、filename、filesize、target。target 为 * 时，在 uploads/ 下以'
         '“发送方_文件名”打开文件并写入后续 CHUNK；否则按昵称查找目标 fd，转发 META/CHUNK/END。'
         'FILE_END 校验已接收字节数并写日志。'),
        ('4.5 日志设计',
         'listening、accept、nick、CHAT、FILE_*、leave、shutdown 等事件带时间戳写入日志，'
         '既供 diagnose.py 分析，也便于答辩时对照截图说明。'),
        ('4.6 错误处理',
         '非法 magic、version 或超长 length 会导致 recv_frame 失败，线程结束并清理会话。'
         '发送失败时从在线表移除对应项，避免反复向半关闭连接写入。主循环可配合超时返回，'
         '以便进程退出时关闭监听套接字。'),
        ('4.7 与协议头文件的协作',
         '甲、乙不得私自改动帧布局。若需扩展类型，应先修订 PROTOCOL.md 与 FrameType 枚举，再同步双端。'
         '业务层只处理完整 Frame，短写短读由 send_frame / recv_frame 屏蔽。'),
        ('4.8 阅读路径建议',
         '阅读 server.cpp 时可按“参数解析 → listen → accept 循环 → client_thread → 按 FrameType 分支”'
         '顺序对照。NICK 分支负责会话建立，CHAT 分支体现广播，FILE_* 分支体现控制面与数据面分离。'),
    ]:
        heading(doc, title, 2)
        p_text(doc, body)

    heading(doc, '第5章 关键实现说明', 1)
    p_text(
        doc,
        '本章结合本人负责的源码说明若干关键路径；完整、未删减的源文件见附录 A。'
        '下列片段摘自协议头文件中的帧头定义，用于对照第 2 章所述 length-prefixed 设计。',
    )
    add_code_block(doc, '\n'.join(PROTO.splitlines()[14:40]))
    p_text(
        doc,
        '服务器主循环在设置好监听套接字后进入 accept；每个新连接交由独立线程处理。'
        '完整实现包含昵称冲突检测、广播复制 fd 列表、文件落盘与中继等逻辑，详见附录 A.2。',
    )

    chapter_run_test(doc, [
        ('02_server.png', '图6-2 服务端监听启动',
         '图6-2 为服务器启动后的监听与业务日志，可见 bind/listen 成功以及对端接入记录。'),
        ('04_file_upload.png', '图6-3 文件传输过程',
         '图6-3 展示文件上传过程及 uploads 目录中生成的落盘文件，对应 FILE_META/CHUNK/END 流程。'),
        ('06_demo_script.png', '图6-4 一键演示脚本运行',
         '图6-4 为一键冒烟脚本 demo.sh 的运行输出，用于验收聊天与文件等基本路径。'),
    ])
    chapter_issues_summary(doc, BLURBS['jia_sum'])

    heading(doc, '附录A 完整源码', 1)
    p_text(
        doc,
        '本附录收录甲角色相关的全部源码，与仓库保持一致，未作删减。'
        '各文件按逻辑小节编排，源码置于浅灰底单列表格中，便于打印阅读。',
    )
    add_appendix_file(
        doc, 'A.1', 'common/protocol.hpp',
        '该头文件由甲乙共用，定义帧类型、帧头布局以及 send_all、recv_all、send_frame、recv_frame。',
        PROTO, 'protocol',
    )
    add_appendix_file(
        doc, 'A.2', 'server/server.cpp',
        '服务器主实现：监听、会话表、广播、文件上传与中继、日志输出。',
        SERVER, 'server',
    )
    add_appendix_file(
        doc, 'A.3', 'server/Makefile',
        '服务端编译规则，指定 C++17 与常用告警选项。',
        MAKE_SERVER, 'generic',
    )

    path = OUT / '答辩报告_甲_服务器_牛昭凯_20241921.docx'
    doc.save(path)
    return path


def build_yi():
    doc = Document()
    setup_doc(doc)
    cover(doc, '乙（客户端）', '乙（待填）', '____________', 'TCP 交互式客户端')
    toc_page(doc, TOC_COMMON + [
        '第4章 客户端详细设计（本人）',
        '第5章 关键实现说明',
        '第6章 编译运行与测试',
        '第7章 联调问题与解决',
        '第8章 个人总结与展望',
        '参考文献',
        '附录A 完整源码',
    ])
    heading(doc, '摘要', 1)
    p_text(doc, BLURBS['yi_abs'])
    p_text(doc, '关键词：TCP 客户端；命令行；多线程收发；文件传输', first_indent=False)

    common_ch123(
        doc,
        '作为乙，本人关注主动打开、用户交互以及接收路径的可用性，使服务器侧能力能够通过'
        '命令行客户端完整展示，并与甲共用同一套帧编解码。',
    )

    heading(doc, '第4章 客户端详细设计（本人）', 1)
    heading(doc, '4.1 线程模型', 2)
    p_text(
        doc,
        '主线程读取标准输入、解析命令并调用 send_frame；专用接收线程循环 recv_frame，'
        '按类型打印消息或写入本地文件。收发分离可避免阻塞在终端输入时无法显示他人消息。',
    )
    heading(doc, '4.2 命令设计', 2)
    add_table(doc, ['命令', '作用'], [
        ['/nick <名>', '登录昵称'],
        ['/say <消息> 或直接输入', '群聊'],
        ['/list', '查询在线用户'],
        ['/sendfile <路径> [目标]', '发送文件；目标省略或 * 表示上传服务器'],
        ['/ping', '心跳'],
        ['/quit', '退出'],
    ])
    for title, body in [
        ('4.3 文件发送与接收',
         '发送侧读取本地文件，先发 FILE_META，再按约 32KiB 分块发送 FILE_CHUNK，最后 FILE_END。'
         '接收侧见到 META 时创建 recv_发送方_文件名，写入 CHUNK，在 END 时关闭文件。'),
        ('4.4 交互提示',
         'SYS、CHAT、LIST 使用可读前缀输出；在未登录时给出先执行 /nick 的提示；'
         '连接失败时打印与 errno 相关的说明。可选写入 client.log，便于与服务器日志对照。'),
        ('4.5 与服务器联调要点',
         '必须先完成 NICK 再发送 CHAT 或 FILE。本机演示主机填 127.0.0.1；局域网演示改为服务器 IP。'
         '端口须与服务器 -p 一致；若 9000 被占用，两端同步改为 9001。'),
        ('4.6 接收线程退出条件',
         'recv_frame 失败（对端关闭或网络错误）时接收线程退出。执行 /quit 时主动 close 套接字，'
         '促使接收循环结束。'),
        ('4.7 命令解析要点',
         '以首字符是否为 / 区分命令与聊天正文。/sendfile 需解析路径与可选目标。'
         '发送大文件时在主线程同步分块，避免再引入第三线程增加复杂度。'),
    ]:
        heading(doc, title, 2)
        p_text(doc, body)

    heading(doc, '第5章 关键实现说明', 1)
    p_text(
        doc,
        '客户端与服务器共用协议头文件。下面摘录接收线程中对 CHAT 与 FILE_* 的处理轮廓；'
        '完整 client.cpp 见附录 A。',
    )
    # short excerpt: recv_loop start
    lines = CLIENT.splitlines()
    excerpt_start = next((i for i, ln in enumerate(lines) if 'void recv_loop' in ln), 58)
    add_code_block(doc, '\n'.join(lines[excerpt_start:excerpt_start + 35]))
    p_text(doc, '主线程侧的命令分发与文件分块发送逻辑篇幅较长，统一放入附录 A.2 阅读。')

    chapter_run_test(doc, [
        ('03_client_chat.png', '图6-2 客户端聊天会话',
         '图6-2 为双客户端聊天会话界面，可见昵称登录后的 CHAT 消息往来。'),
        ('04_file_upload.png', '图6-3 文件传输过程',
         '图6-3 记录客户端发起 /sendfile 后的传输过程及结果提示。'),
        ('06_demo_script.png', '图6-4 一键演示脚本运行',
         '图6-4 显示冒烟脚本驱动客户端完成基本验收时的终端输出。'),
    ])
    chapter_issues_summary(doc, BLURBS['yi_sum'])

    heading(doc, '附录A 完整源码', 1)
    p_text(doc, '本附录收录乙角色相关源码及协作头文件，内容与仓库一致。')
    add_appendix_file(
        doc, 'A.1', 'common/protocol.hpp',
        '与甲共用的帧协议头文件，客户端通过其中的 send_frame / recv_frame 与服务器通信。',
        PROTO, 'protocol',
    )
    add_appendix_file(
        doc, 'A.2', 'client/client.cpp',
        '交互式客户端完整实现，含接收线程、命令解析与文件收发。',
        CLIENT, 'client',
    )
    add_appendix_file(
        doc, 'A.3', 'client/Makefile',
        '客户端编译规则。',
        MAKE_CLIENT, 'generic',
    )

    path = OUT / '答辩报告_乙_客户端.docx'
    doc.save(path)
    return path


def build_bing():
    doc = Document()
    setup_doc(doc)
    cover(doc, '丙（设计与协议文档）', '丙（待填）', '____________', '选题、设计说明书与协议文档')
    toc_page(doc, [
        '摘要',
        '第1章 选题背景与课程要求',
        '第2章 相关网络原理',
        '第3章 系统总体架构与分工',
        '第4章 协议与设计说明书工作（本人）',
        '第5章 文档工作说明',
        '第6章 测试方案与运行证据',
        '第7章 文档联调与版本管理',
        '第8章 个人总结与展望',
        '参考文献',
        '附录A 完整源码与文稿',
    ])
    heading(doc, '摘要', 1)
    p_text(doc, BLURBS['bing_abs'])
    p_text(doc, '关键词：需求分析；协议设计；测试方案；设计说明书', first_indent=False)

    common_ch123(
        doc,
        '作为丙，本人把网络原理写入可交付的设计说明书，并把帧格式固化为 PROTOCOL.md，'
        '使甲乙实现与答辩表述使用同一套术语与字段约定。',
    )
    heading(doc, '2.4 应用层协议设计原则（文档视角）', 2)
    p_text(
        doc,
        '设计时强调四点：可扩展（保留 version 字段）、可调试（类型名写入日志）、'
        '防滥用（最大帧长）、控制与数据分离（META / CHUNK / END）。'
        '载荷字段采用制表符分隔，便于课堂演示，同时保持解析逻辑简单。',
    )

    heading(doc, '第4章 协议与设计说明书工作（本人）', 1)
    heading(doc, '4.1 需求冻结', 2)
    p_text(
        doc,
        '与全组确认功能需求与非功能约束（C++17、WSL、明文传输、课堂规模）。'
        '非目标明确排除 TLS、数据库鉴权、图形界面、NAT 穿透与断点续传，避免范围膨胀。',
    )
    heading(doc, '4.2 帧布局规范', 2)
    add_table(doc, ['偏移', '大小', '字段'], [
        ['0', '2', "magic = 'C''N'"],
        ['2', '1', 'version = 1'],
        ['3', '1', 'type'],
        ['4', '4', 'length（网络字节序）'],
        ['8', 'length', 'payload'],
    ])
    for title, body in [
        ('4.3 时序：登录—聊天—传文件',
         '客户端 connect 成功后发送 NICK，服务器校验后以 SYS 欢迎；随后可进行 CHAT 广播。'
         '文件传输顺序为 FILE_META → 多段 FILE_CHUNK → FILE_END；服务器或目标客户端按约定落盘。'),
        ('4.4 测试方案设计',
         '测试分为单元、集成与验收（demo.sh）。每条用例写明前置条件、步骤、期望与实际结果。'
         '冒烟脚本把验收自动化，降低答辩现场操作失误。'),
        ('4.5 文档对实现的约束',
         '先发布 PROTOCOL.md 草案，甲乙按此编写可编译的空壳。字段变更遵循“文档先改、代码后改”，'
         '避免仅靠口头约定造成双端不一致。'),
        ('4.6 图表与答辩表达',
         '架构说明、帧格式表、Socket API 映射表是答辩的核心材料。说明书中关于粘包的小节应能'
         '脱离具体代码独立讲清。'),
    ]:
        heading(doc, title, 2)
        p_text(doc, body)

    heading(doc, '第5章 文档工作说明', 1)
    p_text(
        doc,
        '本人交付物主要包括选题说明、设计说明书、协议文档与分工进度表。'
        '正文不在此整篇粘贴 Markdown 原文；附录 A 按文件给出全文，采用与源码相同的表格排版，'
        '避免出现代码围栏或“如下所示”一类粘贴痕迹。下面仅摘录协议文档中的帧格式要点供对照。',
    )
    # Extract a small plain excerpt from PROTOCOL.md without markdown fences
    proto_lines = [ln for ln in PROTOCOL_MD.splitlines() if not ln.strip().startswith('```')]
    add_code_block(doc, '\n'.join(proto_lines[:40]))

    heading(doc, '第6章 测试方案与运行证据', 1)
    p_text(doc, '下表为文档侧整理的测试用例；截图为仓库 results/screenshots 中的运行证据。')
    add_table(doc, ['编号', '用例', '步骤', '期望', '结果'], TESTS)
    figs = [
        ('01_build.png', '图6-1 编译与链接成功',
         '图6-1 说明工程可完整编译链接，作为后续功能测试的前提。'),
        ('02_server.png', '图6-2 服务端监听启动',
         '图6-2 对应服务器被动打开与会话日志，可与设计说明书中的时序描述对照。'),
        ('03_client_chat.png', '图6-3 客户端聊天会话',
         '图6-3 验证双端 CHAT 路径与昵称显示是否符合协议约定。'),
        ('04_file_upload.png', '图6-4 文件传输过程',
         '图6-4 对应 FILE_META/CHUNK/END 流程的实际运行结果。'),
        ('05_llm_diagnose.png', '图6-5 大模型诊断输出',
         '图6-5 为丁模块基于服务器日志生成的诊断文本，体现文档中“可观测性”要求。'),
        ('06_demo_script.png', '图6-6 一键演示脚本运行',
         '图6-6 为一键验收脚本的输出，用于核对 README 命令与真实行为一致。'),
    ]
    for n, c, pr in figs:
        add_figure(doc, n, c, pr)
    p_text(doc, '冒烟日志摘录如下，可与图6-2、图6-6 对照。')
    add_code_block(doc, SMOKE_LOG)

    heading(doc, '第7章 文档联调与版本管理', 1)
    for para in ISSUES.split('\n\n'):
        para = para.strip()
        if para:
            p_text(doc, para)
    p_text(
        doc,
        '文档版本应与代码提交可追溯对应。答辩前需核对 README 中的命令与 scripts/ 下真实脚本一致，'
        '避免现场演示与书面说明不符。',
    )
    heading(doc, '第8章 个人总结与展望', 1)
    p_text(doc, BLURBS['bing_sum'])
    heading(doc, '参考文献', 1)
    for i, r in enumerate(REFS, 1):
        p_text(doc, f'[{i}] {r}', first_indent=False)

    heading(doc, '附录A 完整源码与文稿', 1)
    p_text(
        doc,
        '下列文稿与公共协议头文件按文件分节给出全文。Markdown 原文已去除围栏记号，'
        '以普通等宽文本排入表格，便于打印。',
    )
    add_appendix_file(
        doc, 'A.1', 'protocol/PROTOCOL.md',
        '应用层协议说明全文，是甲乙实现与答辩表述的共同依据。',
        '\n'.join(ln for ln in PROTOCOL_MD.splitlines() if not ln.strip().startswith('```')),
        'protocol_md',
    )
    add_appendix_file(
        doc, 'A.2', 'docs/02_设计说明书.md',
        '课程设计说明书全文，涵盖需求、架构、详细设计与测试安排。',
        '\n'.join(ln for ln in DESIGN.splitlines() if not ln.strip().startswith('```')),
        'design',
    )
    add_appendix_file(
        doc, 'A.3', 'docs/01_选题说明.md',
        '选题背景与课程要求对照说明。',
        TOPIC, 'generic',
    )
    add_appendix_file(
        doc, 'A.4', 'docs/03_分工与进度.md',
        '四人分工与进度安排。',
        DIV, 'generic',
    )
    add_appendix_file(
        doc, 'A.5', 'common/protocol.hpp',
        '公共协议头文件，供与文档中的帧布局表对照。',
        PROTO, 'protocol',
    )

    path = OUT / '答辩报告_丙_设计与协议.docx'
    doc.save(path)
    return path


def build_ding():
    doc = Document()
    setup_doc(doc)
    cover(doc, '丁（LLM 与答辩）', '丁（待填）', '____________', 'LLM 日志诊断与答辩组织')
    toc_page(doc, TOC_COMMON + [
        '第4章 LLM 诊断模块设计（本人）',
        '第5章 关键实现说明',
        '第6章 运行演示与诊断结果',
        '第7章 答辩组织与问题预案',
        '第8章 个人总结与展望',
        '参考文献',
        '附录A 完整源码',
    ])
    heading(doc, '摘要', 1)
    p_text(doc, BLURBS['ding_abs'])
    p_text(doc, '关键词：LLM；日志诊断；提示词；课程答辩', first_indent=False)

    common_ch123(
        doc,
        '作为丁，本人强调大语言模型是辅助分析组件，不能替代甲乙的协议与双端实现，'
        '但能把运行日志映射回课程知识点，服务于答辩讲解与问题定位。',
    )

    heading(doc, '第4章 LLM 诊断模块设计（本人）', 1)
    for title, body in [
        ('4.1 目标与边界',
         '目标是读取服务器日志，输出结构化中文诊断，内容包括现象、可能问题、与协议的对应关系、'
         '排查步骤以及答辩可讲的知识点。边界是不修改线上流量、不自动修复，仅做分析。'),
        ('4.2 模块结构',
         '命令行参数包括日志路径、--mock 与 -o 输出路径。处理流程为：读取文本 → 截断过长日志 → '
         '构造 system/user 提示词（嵌入帧格式说明）→ 若指定 mock 或缺少密钥则走规则引擎，'
         '否则调用 Chat Completions 兼容 HTTP 接口。'),
        ('4.3 提示词设计',
         '提示词将角色设定为“计算机网络助教”，要求结合 TCP 粘包、字节序、NICK/CHAT/FILE 帧解释日志，'
         '并禁止编造日志中不存在的行。把协议摘要写入上下文，有助于减少模型幻觉。'),
        ('4.4 Mock 规则引擎',
         '对 listening、accept、nick、CHAT、FILE_、fail、leave 等关键字匹配，生成固定结构的五段报告，'
         '保证无外网条件下仍可演示完整闭环。'),
        ('4.5 环境变量',
         '通过环境变量配置兼容接口，便于在实验室不同网络条件下切换。'),
        ('4.6 与课程“必须使用 LLM”要求的关系',
         '真实 API 与 mock 双模式并存：有条件时调用真实模型，无条件时也能演示诊断输出。'
         '诊断内容紧扣本组协议字段，避免写成与课题无关的泛泛聊天。'),
    ]:
        heading(doc, title, 2)
        p_text(doc, body)
        if title.startswith('4.5'):
            add_table(doc, ['变量', '含义'], [
                ['OPENAI_API_KEY', 'API 密钥；缺失则进入 mock'],
                ['OPENAI_BASE_URL', '兼容端点，默认官方地址'],
                ['OPENAI_MODEL', '模型名，如 gpt-4o-mini'],
            ])

    heading(doc, '第5章 关键实现说明', 1)
    p_text(
        doc,
        'diagnose.py 的入口负责参数解析与模式选择。下面摘录规则引擎中与 listening/accept 相关的判定，'
        '完整脚本见附录 A.1。',
    )
    lines = LLM.splitlines()
    hs = next((i for i, ln in enumerate(lines) if 'def heuristic_findings' in ln), 53)
    add_code_block(doc, '\n'.join(lines[hs:hs + 40]))

    heading(doc, '第6章 运行演示与诊断结果', 1)
    add_figure(
        doc, '05_llm_diagnose.png', '图6-1 大模型诊断输出',
        '图6-1 为 diagnose.py 在 --mock 模式下的诊断输出，可见五段式中文报告结构。',
    )
    add_figure(
        doc, '02_server.png', '图6-2 服务端监听启动',
        '图6-2 为被分析的服务器日志来源界面，诊断输入与此一致。',
    )
    add_figure(
        doc, '06_demo_script.png', '图6-3 一键演示脚本运行',
        '图6-3 显示冒烟流程中已包含诊断步骤，保证演示可一键复现。',
    )
    add_figure(
        doc, '01_build.png', '图6-4 编译与链接成功',
        '图6-4 说明在运行诊断前，C++ 双端已成功编译，系统处于可运行状态。',
    )
    p_text(doc, '下列为冒烟诊断结果全文，可与图6-1 对照。')
    add_code_block(doc, SMOKE_DIAG)
    p_text(doc, '功能与异常用例执行情况见表。')
    add_table(doc, ['编号', '用例', '步骤', '期望', '结果'], TESTS)

    heading(doc, '第7章 答辩组织与问题预案', 1)
    p_text(
        doc,
        '答辩陈述按“选题动机 → 协议要点 → 双端演示 → LLM 诊断 → 分工说明”组织。'
        '下列提纲原文见附录；此处列出常见提问与应答要点。',
    )
    add_table(doc, ['可能提问', '应答要点'], [
        ['为何不用 UDP？', '聊天与文件需要可靠有序；UDP 需自建重传与排序'],
        ['如何解决粘包？', 'length-prefixed 帧；recv_all 收齐头与体'],
        ['为何使用 htonl？', '多机字节序可能不同，长度字段必须用网络序'],
        ['文件很大怎么办？', '分 CHUNK 传输，并限制单帧上限'],
        ['LLM 做了什么？', '读日志并结合协议上下文给出诊断，不替代双端实现'],
        ['四人如何协作？', '先冻结 protocol.hpp；丙出文档；甲乙丁并行开发'],
    ])

    heading(doc, '第8章 个人总结与展望', 1)
    p_text(doc, BLURBS['ding_sum'])
    heading(doc, '参考文献', 1)
    for i, r in enumerate(REFS, 1):
        p_text(doc, f'[{i}] {r}', first_indent=False)

    heading(doc, '附录A 完整源码', 1)
    p_text(doc, '本附录给出丁角色负责的诊断脚本及相关辅助文件全文。')
    add_appendix_file(
        doc, 'A.1', 'llm/diagnose.py',
        'LLM / mock 诊断脚本完整源码。',
        LLM, 'llm',
    )
    add_appendix_file(
        doc, 'A.2', 'llm/requirements.txt',
        'Python 依赖声明（当前实现以标准库为主，此文件便于环境说明）。',
        REQS, 'generic',
    )
    add_appendix_file(
        doc, 'A.3', 'scripts/demo.sh',
        '一键冒烟与演示脚本，内含调用 diagnose.py 的步骤。',
        DEMO_SH, 'generic',
    )
    add_appendix_file(
        doc, 'A.4', 'docs/04_答辩陈述提纲.md',
        '答辩陈述提纲全文。',
        SPEECH, 'generic',
    )
    add_appendix_file(
        doc, 'A.5', 'samples/sample_chat_log.txt',
        '样例日志，可用于离线演示 diagnose.py。',
        SAMPLE_LOG, 'generic',
    )
    heading(doc, 'A.6 results/smoke_server.log', 2)
    p_text(doc, '冒烟运行产生的服务器日志，作为诊断输入之一。')
    add_code_block(doc, SMOKE_LOG)

    path = OUT / '答辩报告_丁_LLM与答辩.docx'
    doc.save(path)
    return path


def write_ascii_copies(paths: list[Path]):
    mapping = [
        ('答辩报告_甲_服务器_牛昭凯_20241921.docx', 'report_jia.docx'),
        ('答辩报告_乙_客户端.docx', 'report_yi.docx'),
        ('答辩报告_丙_设计与协议.docx', 'report_bing.docx'),
        ('答辩报告_丁_LLM与答辩.docx', 'report_ding.docx'),
    ]
    ASCII_OUT.mkdir(parents=True, exist_ok=True)
    out = []
    by_name = {p.name: p for p in paths}
    for cn_name, ascii_name in mapping:
        src = by_name[cn_name]
        dst = ASCII_OUT / ascii_name
        shutil.copy2(src, dst)
        out.append(dst)
    return out


def make_zip(paths: list[Path], ascii_paths: list[Path]):
    zpath = OUT / 'cn_defense_reports.zip'
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zf:
        for p in paths:
            zf.write(p, arcname=p.name)
        for p in ascii_paths:
            zf.write(p, arcname=f'ascii/{p.name}')
    return zpath


def main():
    paths = [build_jia(), build_yi(), build_bing(), build_ding()]
    ascii_paths = write_ascii_copies(paths)
    zpath = make_zip(paths, ascii_paths)
    print('Generated:')
    for p in paths + ascii_paths + [zpath]:
        print(f'{p}  ({p.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
