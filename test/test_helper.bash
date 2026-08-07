#!/usr/bin/env bash
#
# test_helper.bash —— Bats（bats-core）测试公共辅助
#
# 作用：为 run_pipeline.sh 的单元测试与属性测试提供共享脚手架，包含四类能力：
#   1) 受守卫保护地加载主脚本（source 但不触发 main 命令分发）；
#   2) 临时工作目录的创建 / 清理（供 .bats 的 setup / teardown 调用）；
#   3) 外部依赖打桩（stub）：python / python3 / date 等命令，以及可被 source 的
#      虚拟环境 activate 脚本，用于隔离副作用并记录调用参数；
#   4) 轻量随机输入生成器：随机退出码、随机配置键子集、随机目录树、随机日期
#      文件名、随机子命令串、随机日志级别 / 消息等，供「在 bats 用例内循环 ≥100 次
#      迭代」的属性测试驱动使用。
#
# 加载原理：run_pipeline.sh 末尾用 `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]` 守卫，
#       仅在被【直接执行】时才调用 main。当本辅助以 `source` 方式加载它时，
#       BASH_SOURCE[0] 与 $0 不相等，因此 main 不会执行，只定义函数 —— 这是后续
#       任务隔离调用纯逻辑函数（定位器、退出码聚合、日志保留过滤、锁决策等）的关键。
#
# 用法（在 .bats 文件中）：
#   load 'test_helper'
#   setup() {
#       setup_test_workdir          # 准备本用例的临时工作目录
#       load_pipeline_script        # 载入被测函数（不触发 main）
#   }
#   teardown() {
#       teardown_test_workdir       # 清理临时工作目录与 PATH 打桩
#   }
#   @test "示例" { run resolve_project_root "$TEST_WORKDIR"; [ "$status" -eq 0 ]; }
#
# 本地运行方式见 test/README.md：在终端手动执行 `bats test/`。

# =============================================================================
# 路径常量
# =============================================================================

# 测试目录（本文件所在目录）。
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 项目根目录（test/ 的上一级，即 run_pipeline.sh 所在目录）。
PROJECT_ROOT_DIR="$(cd "${TEST_DIR}/.." && pwd)"

# 被测主脚本路径。
PIPELINE_SCRIPT="${PROJECT_ROOT_DIR}/run_pipeline.sh"

# run_pipeline.sh 的全部配置键（与设计文档 Config_File 表保持一致）。
# 供「随机配置键子集」生成器与配置缺省属性测试使用。
PIPELINE_CONFIG_KEYS=(
    PROJECT_ROOT
    VENV_PATH
    PYTHON_BIN
    CSV_DATE_RANGE_ARGS
    LOG_DIR
    LOG_RETENTION_DAYS
    LOCK_FILE
)

# 已知子命令集合（含「空」语义由调用方单独处理）。
# 供「随机未知子命令」生成器排除合法值。
PIPELINE_KNOWN_COMMANDS=(run status --help -h help)

# =============================================================================
# 1) 加载被测主脚本（不触发命令分发）
# =============================================================================

# load_pipeline_script —— source 主脚本以载入其内部函数（不触发 main 分发）。
load_pipeline_script() {
    if [[ ! -f "${PIPELINE_SCRIPT}" ]]; then
        echo "找不到被测脚本: ${PIPELINE_SCRIPT}" >&2
        return 1
    fi
    # shellcheck source=/dev/null
    source "${PIPELINE_SCRIPT}"
}

# =============================================================================
# 2) 临时工作目录创建 / 清理（供 setup / teardown 调用）
# =============================================================================

# setup_test_workdir —— 创建本用例专属的临时工作目录，导出到 TEST_WORKDIR。
# 优先复用 bats 提供的 BATS_TEST_TMPDIR（用例结束自动回收）；否则回退 mktemp。
setup_test_workdir() {
    if [[ -n "${BATS_TEST_TMPDIR:-}" ]]; then
        TEST_WORKDIR="${BATS_TEST_TMPDIR}/work"
        mkdir -p "${TEST_WORKDIR}"
    else
        TEST_WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/run_pipeline_test.XXXXXX")"
    fi
    export TEST_WORKDIR
}

# teardown_test_workdir —— 清理临时工作目录与 PATH 打桩。
# 仅当 TEST_WORKDIR 非空、确为目录、且位于已知临时位置时才删除，避免误删项目目录。
teardown_test_workdir() {
    # 先恢复被打桩污染的 PATH（若有）。
    teardown_stub_path
    local wd="${TEST_WORKDIR:-}"
    if [[ -n "${wd}" && -d "${wd}" ]]; then
        # 仅删除 mktemp 生成的目录，或位于 bats 临时目录之下的工作目录。
        if [[ "${wd}" == *run_pipeline_test* ]] ||
            { [[ -n "${BATS_TEST_TMPDIR:-}" ]] && [[ "${wd}" == "${BATS_TEST_TMPDIR}"/* ]]; }; then
            rm -rf "${wd}"
        fi
    fi
    unset TEST_WORKDIR
}

# =============================================================================
# 3) 外部依赖打桩（stub）
#
# 思路：run_pipeline.sh 通过 `python`/`$PYTHON_BIN` 调用 Python，通过
#       `source "$VENV_PATH/bin/activate"` 激活虚拟环境，通过 `date` 生成时间戳。
#       为隔离这些真实副作用，提供两类打桩：
#         a) PATH 打桩：在临时目录写入同名可执行 stub 脚本并将其目录前置到 PATH，
#            stub 会把每次调用的参数追加记录到调用日志，便于断言命令构造；
#         b) 虚拟环境打桩：生成一个可被 source 的假 activate 脚本（可指定成功/失败）。
# =============================================================================

# setup_stub_path —— 初始化 PATH 打桩目录，并把它前置到 PATH。
# 副作用：导出 STUB_BIN_DIR（stub 脚本存放目录）、STUB_CALLS_LOG（调用记录文件）、
#         _STUB_ORIG_PATH（用于 teardown 还原）。
setup_stub_path() {
    if [[ -z "${TEST_WORKDIR:-}" ]]; then
        setup_test_workdir
    fi
    STUB_BIN_DIR="${TEST_WORKDIR}/stub_bin"
    STUB_CALLS_LOG="${TEST_WORKDIR}/stub_calls.log"
    mkdir -p "${STUB_BIN_DIR}"
    : >"${STUB_CALLS_LOG}"
    _STUB_ORIG_PATH="${_STUB_ORIG_PATH:-${PATH}}"
    export STUB_BIN_DIR STUB_CALLS_LOG _STUB_ORIG_PATH
    export PATH="${STUB_BIN_DIR}:${PATH}"
}

# teardown_stub_path —— 还原打桩前的 PATH（若曾打桩）。
teardown_stub_path() {
    if [[ -n "${_STUB_ORIG_PATH:-}" ]]; then
        export PATH="${_STUB_ORIG_PATH}"
        unset _STUB_ORIG_PATH
    fi
}

# make_command_stub NAME [EXIT_CODE] [STDOUT_TEXT] —— 生成一个名为 NAME 的命令 stub。
# 行为：被调用时把 "NAME <参数...>" 追加到 STUB_CALLS_LOG，按需打印 STDOUT_TEXT，
#       并以 EXIT_CODE（缺省 0）退出。用于打桩 python / python3 等外部命令。
make_command_stub() {
    local name="$1"
    local exit_code="${2:-0}"
    local stdout_text="${3:-}"
    if [[ -z "${STUB_BIN_DIR:-}" ]]; then
        setup_stub_path
    fi
    local stub_path="${STUB_BIN_DIR}/${name}"
    {
        echo '#!/usr/bin/env bash'
        echo "# 自动生成的命令 stub：${name}"
        echo "printf '%s' \"${name}\" >>\"${STUB_CALLS_LOG}\""
        echo 'for _arg in "$@"; do printf " %s" "$_arg" >>"'"${STUB_CALLS_LOG}"'"; done'
        echo "printf '\\n' >>\"${STUB_CALLS_LOG}\""
        if [[ -n "${stdout_text}" ]]; then
            echo "printf '%s\\n' \"${stdout_text}\""
        fi
        echo "exit ${exit_code}"
    } >"${stub_path}"
    chmod +x "${stub_path}"
    echo "${stub_path}"
}

# get_stub_calls —— 输出迄今记录的全部 stub 调用（每行一次调用：NAME 参数...）。
get_stub_calls() {
    if [[ -n "${STUB_CALLS_LOG:-}" && -f "${STUB_CALLS_LOG}" ]]; then
        cat "${STUB_CALLS_LOG}"
    fi
}

# make_fake_venv VENV_DIR [FAIL] —— 在 VENV_DIR 下生成可被 source 的假 activate 脚本。
# 默认生成「激活成功」的脚本（设置标记变量 _FAKE_VENV_ACTIVATED=1）；
# 若第二参数为 "fail"，则生成「激活失败」的脚本（source 时返回非零）。
# 返回（echo）activate 脚本路径。
make_fake_venv() {
    local venv_dir="$1"
    local mode="${2:-ok}"
    mkdir -p "${venv_dir}/bin"
    local activate_path="${venv_dir}/bin/activate"
    if [[ "${mode}" == "fail" ]]; then
        {
            echo '# 假 activate（模拟激活失败）'
            echo 'echo "fake venv activate failed" >&2'
            echo 'return 1 2>/dev/null || exit 1'
        } >"${activate_path}"
    else
        {
            echo '# 假 activate（模拟激活成功）'
            echo 'export _FAKE_VENV_ACTIVATED=1'
            echo 'return 0 2>/dev/null || true'
        } >"${activate_path}"
    fi
    echo "${activate_path}"
}

# stub_date FIXED_OUTPUT —— 打桩 date 命令，使其对任意参数都输出固定文本。
# 用于让带时间戳的日志路径 / 日志行在测试中可预测。
stub_date() {
    local fixed="$1"
    make_command_stub date 0 "${fixed}" >/dev/null
}

# =============================================================================
# 4) 轻量随机输入生成器
#
# 全部基于 bash 内建 $RANDOM，无外部依赖。供属性测试在用例内循环 ≥100 次驱动。
# =============================================================================

# rand_int MIN MAX —— 输出 [MIN, MAX] 闭区间内的随机整数。
rand_int() {
    local min="$1" max="$2" span
    span=$((max - min + 1))
    if ((span <= 0)); then
        echo "${min}"
        return
    fi
    echo $((min + RANDOM % span))
}

# rand_string [LEN] —— 输出长度为 LEN（缺省 8）的随机字母数字串。
rand_string() {
    local len="${1:-8}" chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    local out='' i idx
    for ((i = 0; i < len; i++)); do
        idx=$((RANDOM % ${#chars}))
        out+="${chars:idx:1}"
    done
    echo "${out}"
}

# rand_exit_code —— 输出一个随机退出码（覆盖 0 与非零），约 1/3 概率为 0。
# 供退出码聚合属性测试构造 (CSV, Map) 组合。
rand_exit_code() {
    if ((RANDOM % 3 == 0)); then
        echo 0
    else
        rand_int 1 10
    fi
}

# rand_nonzero_exit_code —— 输出一个随机非零退出码（1-255）。
rand_nonzero_exit_code() {
    rand_int 1 255
}

# rand_log_level —— 从 {INFO, WARN, ERROR} 中随机选择一个日志级别。
rand_log_level() {
    local levels=(INFO WARN ERROR)
    echo "${levels[RANDOM % ${#levels[@]}]}"
}

# rand_config_subset —— 从 PIPELINE_CONFIG_KEYS 中随机挑选一个子集（可能为空集）。
# 输出：被选中的键，每行一个。供「配置缺省」属性测试随机决定哪些键出现在配置文件中。
rand_config_subset() {
    local key
    for key in "${PIPELINE_CONFIG_KEYS[@]}"; do
        if ((RANDOM % 2 == 0)); then
            echo "${key}"
        fi
    done
}

# rand_date_filename —— 生成一个形如 pipeline_YYYYMMDD_HHMMSS.log 的随机日志文件名。
# 日期范围 2020-2030 年、01-12 月、01-28 日（规避非法日），时分秒合法。
rand_date_filename() {
    local y m d hh mm ss
    y=$(rand_int 2020 2030)
    m=$(rand_int 1 12)
    d=$(rand_int 1 28)
    hh=$(rand_int 0 23)
    mm=$(rand_int 0 59)
    ss=$(rand_int 0 59)
    printf 'pipeline_%04d%02d%02d_%02d%02d%02d.log\n' "${y}" "${m}" "${d}" "${hh}" "${mm}" "${ss}"
}

# rand_subcommand —— 生成一个【不属于】已知子命令集合的随机子命令串（非空）。
# 供「未知子命令退出码为 1」属性测试使用。
rand_subcommand() {
    local candidate known is_known
    while :; do
        candidate="$(rand_string "$(rand_int 1 12)")"
        is_known=0
        for known in "${PIPELINE_KNOWN_COMMANDS[@]}"; do
            if [[ "${candidate}" == "${known}" ]]; then
                is_known=1
                break
            fi
        done
        if ((is_known == 0)); then
            echo "${candidate}"
            return
        fi
    done
}

# make_random_dir_chain BASE [MAX_DEPTH] —— 在 BASE 下创建一条随机深度的嵌套目录链，
# 输出（echo）最深一级目录的绝对路径。MAX_DEPTH 缺省 6。
make_random_dir_chain() {
    local base="$1" max_depth="${2:-6}" depth i dir
    depth=$(rand_int 1 "${max_depth}")
    dir="${base}"
    for ((i = 0; i < depth; i++)); do
        dir="${dir}/$(rand_string 5)"
    done
    mkdir -p "${dir}"
    echo "${dir}"
}

# place_project_markers DIR —— 在 DIR 下创建 gencsv/ 与 maps/ 两个标记子目录，
# 使该目录成为一个「有效的 Project_Root」。
place_project_markers() {
    local dir="$1"
    mkdir -p "${dir}/gencsv" "${dir}/maps"
}

# make_random_project_tree BASE —— 生成用于「项目根目录定位」属性测试的随机目录树。
# 随机选择一条目录链，并在链上某个随机层级放置 gencsv/+maps/ 标记。
# 输出两行：
#   第 1 行：起点目录（最深一级），供 resolve_project_root 从此向上查找；
#   第 2 行：期望的有效祖先目录（最近一个同时含 gencsv/ 与 maps/ 的目录）。
#            若本次随机决定「不放置任何标记」，第 2 行为空串（表示应判定为查找失败）。
make_random_project_tree() {
    local base="$1" leaf parent expected_root chain=()
    leaf="$(make_random_dir_chain "${base}")"

    # 收集从 base 到 leaf 的所有层级，便于随机选层放置标记。
    local cur="${leaf}"
    while [[ "${cur}" == "${base}"* && "${cur}" != "${base}" ]]; do
        chain+=("${cur}")
        cur="$(dirname "${cur}")"
    done
    chain+=("${base}")

    # 约 1/5 概率不放置标记 —— 用于覆盖「不存在有效祖先 => 失败」分支。
    if ((RANDOM % 5 == 0)); then
        echo "${leaf}"
        echo ""
        return
    fi

    # 在链上随机选一层放置 gencsv/+maps/，该层即期望的有效祖先。
    local idx="${chain[RANDOM % ${#chain[@]}]}"
    expected_root="${idx}"
    place_project_markers "${expected_root}"
    echo "${leaf}"
    echo "${expected_root}"
}

# write_partial_config FILE [KEY=VALUE...] —— 写出一份只包含给定键值的 pipeline.conf。
# 供「配置缺省」属性测试构造「缺失若干键」的临时配置文件。
write_partial_config() {
    local file="$1"
    shift
    : >"${file}"
    local pair
    for pair in "$@"; do
        # 以 KEY="VALUE" 形式写入，可被 source 安全加载。
        local key="${pair%%=*}" value="${pair#*=}"
        printf '%s="%s"\n' "${key}" "${value}" >>"${file}"
    done
}
