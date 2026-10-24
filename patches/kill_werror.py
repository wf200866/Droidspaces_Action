#!/usr/bin/env python3
"""注释掉 4.19 Makefile 里的 cc-option -Werror 探测行。

4.19 的 Makefile 第 979-991 行：
    KBUILD_CFLAGS += $(call cc-option,-Werror=implicit-int)
    KBUILD_CFLAGS += $(call cc-option,-Werror=strict-prototypes)
    KBUILD_CFLAGS += $(call cc-option,-Werror=date-time)
    KBUILD_CFLAGS += $(call cc-option,-Werror=incompatible-pointer-types)
    KBUILD_CFLAGS += $(call cc-option,-Werror=designated-init)

这些是"探测器"形式：编译器支持才加。它们追加在 KBUILD_CFLAGS 末尾，
所以 KCFLAGS 里写的 -Wno-xxx / -Wno-error 都排在它们前面，压不住。

OPPO/MTK 私有代码里 untouched 变量很多：
    aw87xxx_2_x_0.c:542       'profile' set but not used
    helio-dvfsrc-sysfs.c:254  'dvfsrc' set but not used
都不是逻辑错误。整块注释掉是唯一可靠的做法。
"""
import re
import sys


def main(path):
    src = open(path, encoding="utf-8", errors="surrogateescape").read()
    lines = src.splitlines(keepends=True)
    out = []
    n = 0
    for ln in lines:
        # 只匹配「激活状态」的 cc-option -Werror 行，已有 # 前缀的跳过
        if re.match(r"^\s*KBUILD_CFLAGS\s*\+=\s*\$\(call\s+cc-option\s*,", ln) and "-Werror=" in ln:
            out.append("# [cph2605] " + ln)
            n += 1
        else:
            out.append(ln)
    open(path, "w", encoding="utf-8", errors="surrogateescape").write("".join(out))
    left = sum(
        1
        for ln in "".join(out).splitlines()
        if re.match(r"^\s*KBUILD_CFLAGS\s*\+=\s*\$\(call\s+cc-option", ln) and "-Werror=" in ln
    )
    print("[vendor] disabled %d cc-option -Werror lines, %d remaining active" % (n, left))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))