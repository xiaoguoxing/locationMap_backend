#!/usr/bin/env bats
#
# load_config.bats —— 配置加载器 load_config 的测试（任务 2.2 / 2.3）
#
# 覆盖：
#   - 任务 2.2 属性测试：Property 2 配置缺省（≥100 次迭代）
#   - 任务 2.3 边界/错误用例：非法配置 → exit 1 且错误入日志/stderr
#
# 本地运行：在项目根目录执行 `bats test/`（须在 Linux/bash 环境）。
#
# 说明：run_pipeline.sh 顶部 set -u（引用未定义变量即报错），被 source 后该选项
#       对本测试 shell 同样生效，故下方读取变量处统一用 ${VAR:-} / ${arr[k]+x} 等
#       安全写法规避「未绑定变量」错误。

load 'test_helper'

setup() {
    setup_test_workdir
    load_pipeline_script
}

teardown() {
    teardown_test_workdir
}

# unset_all_config_keys —— 清空全部配置键与 PIPELINE_CONF，保证每次迭代从干净状态开始。
# 必要性：load_config 用 `: "${KEY:=默认值}"` 兜底，仅在键「未设置或为空」时赋默认值；
#         若上一轮迭代遗留了非空值，本轮缺省逻辑将不会生效，导致断言读到陈旧值。
unset_all_config_keys() {
    unset "${PIPELINE_CONFIG_KEYS[@]}" 2>/dev/null || true
    unset PIPELINE_CONF 2>/dev/null || true
}

# expected_default_for KEY FINAL_PROJECT_ROOT —— 返回某键在「文件未提供」时的预定义缺省值。
# FINAL_PROJECT_ROOT 为本轮最终生效的 PROJECT_ROOT（影响 VENV_PATH/LOG_DIR/LOCK_FILE）。
expected_default_for() {
    local key="$1" pr="$2"
    case "$key" in
        PROJECT_ROOT) printf '%s' "" ;;
        PYTHON_BIN) printf '%s' "python3" ;;
        CSV_DATE_RANGE_ARGS) printf '%s' "--days 30 --range-days 7" ;;
        LOG_RETENTION_DAYS) printf '%s' "7" ;;
        VENV_PATH) [[ -n "$pr" ]] && printf '%s' "$pr/venv" || printf '%s' "" ;;
        LOG_DIR) [[ -n "$pr" ]] && printf '%s' "$pr/logs/pipeline" || printf '%s' "" ;;
        LOCK_FILE) [[ -n "$pr" ]] && printf '%s' "$pr/run_pipeline.lock" || printf '%s' "" ;;
    esac
}

# Feature: scheduled-csv-html-pipeline, Property 2: 对任意缺失若干配置键的 Config_File，
# load_config 加载后每个未在文件中提供的键恰好取其预定义缺省值，文件提供的键保留其值。
# Validates: Requirements 2.2, 5.2
@test "Property 2: 配置缺省 —— 缺失键取缺省值，提供键保留其值（≥100 次迭代）" {
    local iterations=100 i
    for ((i = 0; i < iterations; i++)); do
        unset_all_config_keys

        # 1) 随机决定本轮哪些键出现在配置文件中。
        local subset=()
        mapfile -t subset < <(rand_config_subset)

        # 2) 为被选中的键生成「合法」的提供值，并记入 provided 关联数组。
        declare -A provided=()
        local pairs=() key value
        if ((${#subset[@]} > 0)); then
            for key in "${subset[@]}"; do
                case "$key" in
                    LOG_RETENTION_DAYS) value="$(rand_int 0 365)" ;; # 必须为非负整数
                    *) value="v$(rand_string 6)" ;;                  # 非空字母数字串
                esac
                provided["$key"]="$value"
                pairs+=("${key}=${value}")
            done
        fi

        # 3) 写出仅含上述键的临时 pipeline.conf，并通过 PIPELINE_CONF 指向它。
        local conf="${TEST_WORKDIR}/pipeline_${i}.conf"
        write_partial_config "$conf" "${pairs[@]:-}"
        export PIPELINE_CONF="$conf"

        # 4) 加载配置（本轮全部为合法值，load_config 不会退出）。
        load_config

        # 5) 计算本轮最终 PROJECT_ROOT（影响依赖型缺省）。
        local final_pr
        if [[ ${provided[PROJECT_ROOT]+x} == x ]]; then
            final_pr="${provided[PROJECT_ROOT]}"
        else
            final_pr=""
        fi

        # 6) 逐键断言：提供键==提供值；缺失键==预定义缺省值。
        for key in "${PIPELINE_CONFIG_KEYS[@]}"; do
            local actual="${!key:-}" expected
            if [[ ${provided[$key]+x} == x ]]; then
                expected="${provided[$key]}"
            else
                expected="$(expected_default_for "$key" "$final_pr")"
            fi
            [ "$actual" = "$expected" ] || {
                echo "迭代 $i 键 $key 不匹配：期望='$expected' 实际='$actual'" >&2
                echo "本轮配置文件内容：" >&2
                cat "$conf" >&2
                return 1
            }
        done

        unset provided
    done
}

# ---------------------------------------------------------------------------
# 任务 2.3：非法配置边界/错误用例 —— 非法时 exit 1 且错误入日志/stderr
# Validates: Requirements 5.3, 10.2
# ---------------------------------------------------------------------------

@test "边界: LOG_RETENTION_DAYS 为负数 → exit 1 且错误提及该键" {
    local conf="${TEST_WORKDIR}/bad_neg.conf"
    write_partial_config "$conf" 'LOG_RETENTION_DAYS=-5'
    export PIPELINE_CONF="$conf"

    run load_config
    [ "$status" -eq 1 ]
    [[ "$output" == *LOG_RETENTION_DAYS* ]]
}

@test "边界: LOG_RETENTION_DAYS 为非整数 → exit 1 且错误提及该键" {
    local conf="${TEST_WORKDIR}/bad_nan.conf"
    write_partial_config "$conf" 'LOG_RETENTION_DAYS=abc'
    export PIPELINE_CONF="$conf"

    run load_config
    [ "$status" -eq 1 ]
    [[ "$output" == *LOG_RETENTION_DAYS* ]]
}

@test "边界: LOG_RETENTION_DAYS 为小数 → exit 1" {
    local conf="${TEST_WORKDIR}/bad_float.conf"
    write_partial_config "$conf" 'LOG_RETENTION_DAYS=3.5'
    export PIPELINE_CONF="$conf"

    run load_config
    [ "$status" -eq 1 ]
}

@test "缺省: 配置文件不存在时全部走缺省值且不报错（PIPELINE_CONF 指向缺失文件）" {
    export PIPELINE_CONF="${TEST_WORKDIR}/does_not_exist.conf"

    load_config
    [ "${LOG_RETENTION_DAYS}" = "7" ]
    [ "${PYTHON_BIN}" = "python3" ]
    [ "${CSV_DATE_RANGE_ARGS}" = "--days 30 --range-days 7" ]
}

# 说明（设计张力）：任务要求对 CSV_DATE_RANGE_ARGS 用 `: "${KEY:=默认值}"` 兜底，
# 带冒号的 := 会把「空字符串」也视为未设置并替换为默认值；因此通过配置文件把
# CSV_DATE_RANGE_ARGS 设为空字符串时，其结果会回退到缺省值（而非触发非空校验）。
# 本用例据实断言该「空 → 回退缺省」的实际行为；load_config 中的非空校验为防御性分支。
@test "缺省: 配置中 CSV_DATE_RANGE_ARGS 为空字符串时回退缺省值（:= 语义）" {
    local conf="${TEST_WORKDIR}/empty_csv.conf"
    write_partial_config "$conf" 'CSV_DATE_RANGE_ARGS='
    export PIPELINE_CONF="$conf"

    load_config
    [ "${CSV_DATE_RANGE_ARGS}" = "--days 30 --range-days 7" ]
}
