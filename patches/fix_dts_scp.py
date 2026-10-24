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
    """把 scp/include/ 下的全部头文件铺到所有会 include 它们的目录。

    为什么不能只靠文本扫描
    ----------------------
    引用链是闭包式的：
        rv/scp_feature_define.h  --include "scp.h"-->  scp.h
        scp.h                    --include "scp_rv.h"--> scp_rv.h

    两个都是引号形式，编译器以「当前文件所在目录」为第一搜索路径。
    一旦 scp.h 通过软链出现在 rv/ 下，rv/ 就必须同时能看到 scp_rv.h，
    否则报 fatal error: 'scp_rv.h' file not found。
    而 scp_rv.h 这个名字只出现在 include/ 里的 scp.h 内部，
    从 rv/ 下的 .c 文件扫不到，所以文本扫描会漏。

    做法：凡是 include/ 里任意头文件被某目录引用，就把 include/ 下
    全部头文件都链到那个目录。数量只有 3 个，铺开无副作用。
    """
    base = os.path.join(root, "drivers/misc/mediatek/scp")
    inc = os.path.join(base, "include")
    if not os.path.isdir(inc):
        print("[scp] WARN: %s not found, skipping" % inc)
        return 0

    headers = sorted(f for f in os.listdir(inc) if f.endswith(".h"))
    if not headers:
        print("[scp] WARN: no headers in %s" % inc)
        return 0
    print("[scp] include/ has %d header(s): %s" % (len(headers), ", ".join(headers)))

    # 找出所有引用了 include/ 里任意头文件的目录（引号形式）
    pat = re.compile(
        r'#include\s+"(' + "|".join(re.escape(h) for h in headers) + r')"'
    )
    targets = set()
    for dirpath, _, filenames in os.walk(base):
        if os.path.abspath(dirpath) == os.path.abspath(inc):
            continue
        for fn in filenames:
            if not fn.endswith((".c", ".h")):
                continue
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8",
                          errors="surrogateescape") as f:
                    content = f.read()
            except OSError:
                continue
            if pat.search(content):
                targets.add(dirpath)
                break

    linked = 0
    for d in sorted(targets):
        for h in headers:
            link = os.path.join(d, h)
            if os.path.lexists(link):
                continue
            rel = os.path.relpath(os.path.join(inc, h), d)
            try:
                os.symlink(rel, link)
                linked += 1
            except OSError as e:
                print("[scp] WARN: cannot link %s: %s" % (link, e))
        print("[scp] staged %d header(s) into %s" % (len(headers), os.path.relpath(d, root)))

    print("[scp] total links created: %d" % linked)
    return 0


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    fix_dts(root)
    fix_scp_include(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())