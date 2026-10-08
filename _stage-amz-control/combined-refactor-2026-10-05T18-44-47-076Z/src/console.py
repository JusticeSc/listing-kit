#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""控制台编码归一 —— 让每个入口在 Windows 默认代码页下也不炸。

这是一次**实测事故**的修法，不是预防性设计
------------------------------------------
2026-09-23，在**干净虚拟环境**里按 README 的命令跑：

    UnicodeEncodeError: 'gbk' codec can't encode character '\u2713'

`\u2713` / `\u2717`（对勾与叉）不在 cp936 里，而 Windows 上 Python 的
stdout 默认跟着控制台代码页走。更糟的是 `tools/check_docs.py` **自己**也在
`print(f"  \u2717 {s}")` 上崩：**守卫在"该报错"的时候崩掉，是最坏的一种失败** ——
屏幕上是一段 traceback，而不是"哪几条不通过"，人很容易把它读成"守卫坏了"。

为什么不能只在文档里写 `set PYTHONUTF8=1`
------------------------------------------
那是一个**靠人记得的环境变量**。忘了就没有；而且本项目要交给 2–5 名运营人员
独立使用（见 Product V1 目标），不能要求他们记住这个。所以归一化写进入口自己。

**更隐蔽的一点**：`PYTHONUTF8=1` 会让守卫"看起来通过" —— 因为守卫是去
真跑 README 里的命令的，环境变量一开，子进程就不崩了。于是这个缺陷能被
一条"全绿"的报告完全盖住。本项目管这叫**假绿**，比红更危险。

两件事必须一起做
----------------
① `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")`
   保证**写出去**的字节是 UTF-8，且遇到编不出的字符降级而不是抛异常。
② `SetConsoleOutputCP(65001)`，**只在真有控制台时**
   保证**控制台按 UTF-8 解释**这些字节。

只做 ①：cp936 控制台上中文与符号会显示成乱码。
只做 ②：输出被重定向到管道/文件时仍然按 locale 编码，照样崩
（`check_docs` 捕获子进程输出正是这种情形）。

被重定向时不做 ② —— 改父进程的控制台代码页是副作用，不该由子进程来付。
"""
from __future__ import annotations

import sys


def enable_utf8() -> None:
    """把本进程的 stdout/stderr 固定成 UTF-8，并在真控制台上切到 65001。

    幂等：重复调用无副作用。任何一步失败都**吞掉异常继续** ——
    编码归一失败不该让程序起不来（那等于用一个新故障换掉一个旧故障）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass          # 宿主换掉了 stdout（非 TextIOWrapper）：不动它
    try:
        if getattr(sys.stdout, "isatty", None) and sys.stdout.isatty():
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass              # 非 Windows / 没有 kernel32：跳过
