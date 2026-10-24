#!/usr/bin/env bash
# ============================================================================
# CPH2605 (MT6833 / Linux 4.19.191) — vendor 依赖树接线
#
# 这棵 OPPO 源码树里有 52 个私有软链，形如：
#   kernel/sched_assist        -> ../../vendor/oplus/kernel/oplus_performance/sched_assist/
#   arch/arm64/kernel/rootguard -> ../../../../vendor/oplus/kernel/secureguard/rootguard/
#
# 解析基准是软链所在目录。以 KERNEL_DIR/kernel/sched_assist 为例：
#   ../../ 从 KERNEL_DIR/kernel/ 向上两级 = WORKSPACE
#   所以 ../../vendor/ 落在 ${WORKSPACE}/vendor
#
# 官方仓库不发布 vendor 内容，必须单独克隆
# android_kernel_modules_oneplus_mt6833 并放到那个位置。
#
# 不接上的话，任何 make <defconfig> 都会立刻死在：
#   init/Kconfig:740: can't open file "kernel/sched_assist/Kconfig"
#
# 本文件由 5kind/Droidspaces_Action 以 `. ${REPO_ROOT}/patches/custom.sh`
# 的方式 source 执行，因此 EXIT 会正确终止整个 job。
# ============================================================================

set +e

VENDOR_REPO="https://github.com/OnePlusOSS/android_kernel_modules_oneplus_mt6833"
VENDOR_BRANCH="oneplus/mt6833_u_14.0.0_nord_n30_se_5g"
MODS="${WORKSPACE}/_mt6833_mods"

echo "[vendor] KERNEL_DIR = ${KERNEL_DIR}"
echo "[vendor] WORKSPACE  = ${WORKSPACE}"

if [ -z "${KERNEL_DIR}" ] || [ ! -d "${KERNEL_DIR}" ]; then
    echo "[vendor] FATAL: KERNEL_DIR not set or missing"
    exit 1
fi

# ---------------------------------------------------------------- 克隆依赖树 ---
if [ ! -d "${MODS}/vendor" ]; then
    rm -rf "${MODS}"
    echo "[vendor] cloning ${VENDOR_REPO} @ ${VENDOR_BRANCH}"
    git clone --depth 1 --single-branch -b "${VENDOR_BRANCH}" \
        "${VENDOR_REPO}" "${MODS}"
    if [ $? -ne 0 ] || [ ! -d "${MODS}/vendor" ]; then
        echo "[vendor] FATAL: clone failed - kernel cannot build without vendor tree"
        exit 1
    fi
else
    echo "[vendor] reusing existing ${MODS}"
fi

# ------------------------------------------------------------------ 建软链 ---
# 1) WORKSPACE/vendor  ->  mods/vendor      （让 ../../vendor 能解析）
# 2) vendor/kernel-4.19 -> KERNEL_DIR        （部分头文件走 kernel-4.19 前缀）
rm -f  "${WORKSPACE}/vendor"
ln -sfn "${MODS}/vendor" "${WORKSPACE}/vendor"
ln -sfn "${KERNEL_DIR}"  "${WORKSPACE}/vendor/kernel-4.19"

ls -ld "${WORKSPACE}/vendor" "${WORKSPACE}/vendor/kernel-4.19"

# ------------------------------------------------------------------ 自检 ---
broken=$(find "${KERNEL_DIR}" -maxdepth 4 -xtype l 2>/dev/null | wc -l)
echo "[vendor] broken symlinks under KERNEL_DIR (maxdepth 4): ${broken}"
if [ "${broken}" != "0" ]; then
    find "${KERNEL_DIR}" -maxdepth 4 -xtype l 2>/dev/null | head -10
fi

# 实际硬依赖是两个 Kconfig：init/Kconfig 里直接 source 它们。
# 注意：include/linux/sched_assist.h 不需要在这里单独断言，
# 它要么在源码树里，要么经 vendor 软链解析，Kconfig 通过就代表接线正确。
fail=0
for p in kernel/sched_assist/Kconfig kernel/locking/klockopt/Kconfig; do
    if [ -e "${KERNEL_DIR}/${p}" ]; then
        echo "[vendor] OK   ${p}"
    else
        echo "[vendor] MISS ${p}"
        fail=1
    fi
done

# VERMAGIC_STRING 所在文件必须存在
if [ -e "${KERNEL_DIR}/include/linux/vermagic.h" ]; then
    echo "[vendor] OK   include/linux/vermagic.h"
else
    echo "[vendor] WARN include/linux/vermagic.h missing"
fi

if [ "${fail}" != "0" ]; then
    echo "[vendor] FATAL: vendor wiring incomplete, defconfig will fail"
    exit 1
fi

echo "[vendor] wiring complete"
