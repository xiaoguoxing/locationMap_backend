#!/bin/bash
#
# run_static_checks.sh —— 对 run_pipeline.sh 执行静态检查
#
# 检查项：
#   1) bash -n run_pipeline.sh   —— 语法检查（必做，失败即非 0 退出）
#   2) shellcheck run_pipeline.sh —— 静态分析（可选；未安装 shellcheck 时仅警告，不硬失败，
#                                    因为开发环境可能为 Windows，对应需求 1.6 的可移植性考量）
#
# 用法：
#   ./test/run_static_checks.sh
#
# 退出码：
#   0  全部已执行的检查通过（shellcheck 缺失视为通过并给出警告）
#   非 0  bash -n 语法检查失败，或 shellcheck 已安装但报告了问题

set -u

# 定位项目根目录（本脚本位于 test/ 之下）。
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT_DIR="$(cd "${TEST_DIR}/.." && pwd)"
TARGET_SCRIPT="${PROJECT_ROOT_DIR}/run_pipeline.sh"

status=0

if [[ ! -f "${TARGET_SCRIPT}" ]]; then
    echo "[ERROR] 找不到目标脚本: ${TARGET_SCRIPT}" >&2
    exit 1
fi

# --- 1) bash -n 语法检查 ---
echo "[INFO] 运行 bash -n 语法检查: ${TARGET_SCRIPT}"
if bash -n "${TARGET_SCRIPT}"; then
    echo "[OK] bash -n 语法检查通过。"
else
    echo "[ERROR] bash -n 语法检查失败。" >&2
    status=1
fi

# --- 2) shellcheck 静态分析（可选）---
if command -v shellcheck >/dev/null 2>&1; then
    echo "[INFO] 运行 shellcheck: ${TARGET_SCRIPT}"
    if shellcheck "${TARGET_SCRIPT}"; then
        echo "[OK] shellcheck 检查通过。"
    else
        echo "[ERROR] shellcheck 报告了问题。" >&2
        status=1
    fi
else
    echo "[WARN] 未检测到 shellcheck，跳过静态分析（请在 Linux 部署环境中安装后再次检查）。"
fi

exit "${status}"
