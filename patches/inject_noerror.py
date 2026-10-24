#!/usr/bin/env python3
"""在 Kbuild 编译命令的最末端追加 -Wno-error。

为什么必须在 scripts/Makefile.lib 里改
--------------------------------------
4.19 的编译命令由 scripts/Makefile.lib 的 c_flags 组装：

    c_flags = -Wp,-MD,$(depfile) $(NOSTDINC_FLAGS) $(LINUXINCLUDE) \
              -include $(srctree)/include/linux/compiler_types.h \
              $(__c_flags) $(modkern_cflags) \
              $(basename_flags) $(modname_flags)

__c_flags 内部展开顺序是：

    $(KBUILD_CPPFLAGS) $(KBUILD_CFLAGS) $(ccflags-y) ...

而 KBUILD_CFLAGS 里包含：
    KBUILD_CFLAGS := -Wall ... -Werror=...        (Makefile:439)
    KBUILD_CFLAGS += $(call cc-option,-Werror=...) (Makefile:979-991)
    KBUILD_CFLAGS += $(ARCH_CFLAGS) $(KCFLAGS)     (Makefile:1007)

MTK/OPPO 的驱动又在子目录 Makefile 里追加：
    ccflags-y        += -Werror      (tfa98xx/Makefile:22)
    subdir-ccflags-y += -Werror      (charger_ic/Makefile:14)

这些写法位置、变量名、条件形式各不相同，逐个清理总有漏网。
在 c_flags 最末尾追加 -Wno-error 是唯一能兜住全部来源的办法：
clang 处理参数是从左到右、后者覆盖前者，最末尾的 -Wno-error 让所有
先前的 -Werror 全部失效。

副作用：告警不再中断编译。这是为适配 OPPO/MTK 私有代码的必要权衡，
不改变任何运行期语义。
"""
import re
import sys


def main(path):
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        src = f.read()

    if "CPH2605_NOERROR" in src:
        print("[noerror] already patched")
        return 0

    # 匹配 c_flags 赋值块的结尾（$(basename_flags) $(modname_flags)）
    pat = re.compile(
        r"(c_flags\s*=\s*-Wp,-MD,\$\(depfile\).*?\$\(basename_flags\)\s*\$\(modname_flags\))",
        re.S,
    )
    m = pat.search(src)
    if not m:
        print("[noerror] FATAL: c_flags definition not found")
        return 1

    new_block = m.group(1) + " -Wno-error  # CPH2605_NOERROR"
    src = src[: m.start(1)] + new_block + src[m.end(1) :]

    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(src)

    print("[noerror] c_flags now ends with -Wno-error")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))