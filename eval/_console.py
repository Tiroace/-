"""控制台编码兜底（Windows GBK 坑）。

本机 PATH 里的 python 可能是其它软件自带的，控制台默认 GBK；脚本里打印的 ✅/❌
会抛 UnicodeEncodeError 让整个评测崩溃、退出码 1，看起来像「评测失败」，其实
只是编码问题。这里在入口把 stdout/stderr 切到 UTF-8，且不因个别字符失败而中断。
"""
from __future__ import annotations

import sys


def safe_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # 被重定向到不支持 reconfigure 的对象时忽略，不影响评测本身
            pass


if __name__ == "__main__":
    safe_console()
    print("✅ ✅ console ok（中文也正常）")
