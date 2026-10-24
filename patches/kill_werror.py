#!/usr/bin/env python3
"""清除内核树里会污染编译命令的 -Werror。

为什么必须这么做
----------------
Kbuild 的追加顺序（后出现的覆盖先出现的）：

    KBUILD_CFLAGS := -Wall -Wundef ... -Werror=...      (Makefile:439)
    KBUILD_CFLAGS += $(call cc-option,-Werror=...)      (Makefile:979-991)
    KBUILD_CFLAGS += $(ARCH_CFLAGS) $(KCFLAGS)          (Makefile:1007)
    KBUILD_CFLAGS += $(ccflags-y)                       (子目录 Makefile，最后)

子目录 Makefile 里的 ccflags-y += -Werror 排在最后，位置比 KCFLAGS 还靠后，
所以从 KCFLAGS / EXTRA_CMDS 里加 -Wno-error 永远压不住。

MTK / OPPO 私有驱动大量这样写，例如：
    drivers/devfreq/helio-dvfsrc-v3/Makefile:13
        ccflags-y += -Werror -I$(srctree)/drivers/devfreq

配合 OPPO 代码里 untouched 变量（aw87xxx 的 profile、helio-dvfsrc 的 dvfsrc），
每一条都变成致命错误。

本脚本只处理会进入编译命令的赋值行：ccflags-y / asflags-y / subdir-ccflags-y /
subdir-asflags-y / CFLAGS_xxx。不动其它内容，不改语义，只是让告警不再致命。
"""
import os
import re
import sys

# 只改这些形式的行（Kbuild 会展开进编译命令）
TARGET_VAR = re.compile(
    r"^\s*(?:"
    r"ccflags-[ym]|asflags-[ym]|subdir-ccflags-[ym]|subdir-asflags-[ym]"
    r"|CFLAGS_[A-Za-z0-9_]+|ccflags|asflags"
    r")\s*[+:?]?="
)
# 匹配独立的 -Werror 或 -Werror=xxx
WERROR = re.compile(r"(?<![\w-])-Werror(?:=[A-Za-z0-9_-]+)?")


def scan(root):
    changed = []
    total_hits = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "out", "output")]
        for fn in filenames:
            if fn != "Makefile" and not fn.endswith(".mk"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8", errors="surrogateescape") as f:
                    lines = f.readlines()
            except OSError:
                continue
            hit = 0
            out = []
            for ln in lines:
                if TARGET_VAR.match(ln) and WERROR.search(ln):
                    new = WERROR.sub("", ln)
                    new = re.sub(r"[ \t]{2,}", " ", new)
                    out.append(new)
                    hit += 1
                else:
                    out.append(ln)
            if hit:
                with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
                    f.writelines(out)
                changed.append((os.path.relpath(path, root), hit))
                total_hits += hit
    return changed, total_hits


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    changed, total = scan(root)
    for rel, n in changed[:25]:
        print("[werror] %-70s %d line(s)" % (rel, n))
    if len(changed) > 25:
        print("[werror] ... and %d more files" % (len(changed) - 25))
    print("[werror] files changed: %d, lines changed: %d" % (len(changed), total))
    return 0


if __name__ == "__main__":
    sys.exit(main())