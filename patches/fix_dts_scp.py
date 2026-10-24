#!/usr/bin/env python3
"""修掉两个 OPPO/MTK 源码树的固有缺陷，让 arm64 内核能编过。

问题一：OPPO 不发布的定制 dtsi
------------------------------
arch/arm64/boot/dts/mediatek/oplus6833_20015.dts:1407:
    #include "oplus6833_20015/cust.dtsi"

这个 cust.dtsi 是 OPPO 的定制设备树片段，开源仓里没有，也不会有。
只要 dtbs 参与编译就必然 fatal error。

本项目的屏幕/触控/充电 IC/传感器设备树全部来自 boot.img 内已有的 dtb 段
和 dtbo 分区，两者都不改、原样保留。所以正确做法不是补出这个 dtsi，
而是把它从编译列表里摘掉——我们不生产 dtb。

问题二：scp.h 缺少头文件搜索路径
--------------------------------
drivers/misc/mediatek/scp/rv/scp_awake.c:38:  #include "scp.h"
实际文件在 drivers/misc/mediatek/scp/include/scp.h

KCFLAGS 里写 -I 对头文件搜索无效，因为 KCFLAGS 在 KBUILD_CFLAGS 里
展开得太晚，且不参与 ccflags 的 include 路径收集。必须在子目录 Makefile
的 ccflags-y 里加。
"""
import os
import re
import sys


def fix_dts(root):
    """把引用 cust.dtsi 的 dts 从 Makefile 编译列表里注释掉。"""
    dts_dir = os.path.join(root, "arch/arm64/boot/dts/mediatek")
    mk = os.path.join(dts_dir, "Makefile")
    if not os.path.isfile(mk):
        print("[dts] WARN: %s not found" % mk)
        return 0

    # 找出所有引用了 cust.dtsi 的 dts 文件名
    bad = set()
    for fn in os.listdir(dts_dir):
        if not fn.endswith(".dts"):
            continue
        path = os.path.join(dts_dir, fn)
        try:
            with open(path, encoding="utf-8", errors="surrogateescape") as f:
                content = f.read()
        except OSError:
            continue
        if re.search(r'#include\s+"[^"]*cust\.dtsi"', content):
            bad.add(fn[:-4])  # 去掉 .dts

    if not bad:
        print("[dts] no dts referencing cust.dtsi")
        return 0

    print("[dts] dts referencing missing cust.dtsi: %s" % ", ".join(sorted(bad)))

    with open(mk, encoding="utf-8", errors="surrogateescape") as f:
        lines = f.readlines()

    out = []
    disabled = 0
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("#"):
            out.append(ln)
            continue
        # 形如: dtb-$(CONFIG_...) += oplus6833_20015.dtb
        #       always-y += xxx.dtb
        hit = False
        for name in bad:
            if re.search(r"\b" + re.escape(name) + r"\.dtb\b", ln):
                hit = True
                break
        if hit:
            out.append("# [cph2605] " + ln)
            disabled += 1
        else:
            out.append(ln)

    with open(mk, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.writelines(out)

    print("[dts] disabled %d Makefile line(s) referencing those dtbs" % disabled)
    return 0


def fix_scp_include(root):
    """把 scp.h 放进真正需要它的目录。

    drivers/misc/mediatek/scp/rv/scp_feature_define.h:9
    drivers/misc/mediatek/scp/cm4/scp_feature_define.h:12
        #include "scp.h"        <- 引号形式，编译器先搜当前目录

    而 scp.h 实际在 ../include/scp.h。引号 include 先在本目录找，
    找不到才走 -I 列表。最稳的做法是在每个需要它的目录里放同名软链接。
    这比依赖各子目录的 ccflags-y 可靠，不受 Makefile 差异影响。
    """
    base = os.path.join(root, "drivers/misc/mediatek/scp")
    real = os.path.join(base, "include/scp.h")
    if not os.path.isfile(real):
        print("[scp] WARN: %s not found, skipping" % real)
        return 0

    targets = set()
    for dirpath, _, filenames in os.walk(base):
        if "scp_feature_define.h" not in filenames:
            continue
        if os.path.isfile(os.path.join(dirpath, "scp.h")):
            continue
        targets.add(dirpath)

    for d in sorted(targets):
        link = os.path.join(d, "scp.h")
        rel = os.path.relpath(real, d)
        try:
            os.symlink(rel, link)
            print("[scp] linked %s -> %s" % (os.path.relpath(link, root), rel))
        except OSError as e:
            print("[scp] WARN: cannot link %s: %s" % (link, e))

    if not targets:
        print("[scp] nothing to link")
    return 0


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    fix_dts(root)
    fix_scp_include(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())