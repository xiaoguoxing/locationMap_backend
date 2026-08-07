#!/usr/bin/env bats
#
# resolve_project_root.bats —— 项目根目录定位器 resolve_project_root 的测试（任务 3.2 / 3.3）
#
# 覆盖：
#   - 任务 3.2 属性测试：Property 3 项目根目录定位返回最近的有效祖先（≥100 次迭代）
#   - 任务 3.3 边界/错误用例：不含 gencsv/ 或 maps/ 的目录树 → exit 2
#   - 补充：情形 A（配置显式提供 PROJECT_ROOT）的校验通过 / 失败
#
# 本地运行：在项目根目录执行 `bats test/`（须在 Linux/bash 环境）。
#
# 说明：run_pipeline.sh 顶部 set -u（引用未定义变量即报错），被 source 后该选项
#       对本测试 shell 同样生效，故下方读取/清理变量处统一用安全写法规避未绑定变量错误。
#       resolve_project_root 的副作用是 cd 与设置 PROJECT_ROOT，并在失败时 exit 2；
#       因此测试统一借助 bats 的 `run`（在子 shell 执行）隔离 cd / exit 的副作用。

load 'test_helper'

setup() {
    setup_test_workdir
    load_pipeline_script
}

teardown() {
    teardown_test_workdir
}

# reset_root_state —— 每次迭代前清空 PROJECT_ROOT 及其依赖型缺省键，
# 保证从「未显式提供 PROJECT_ROOT」的干净状态开始，强制走情形 B（自动向上查找）。
reset_root_state() {
    unset PROJECT_ROOT VENV_PATH LOG_DIR LOCK_FILE 2>/dev/null || true
}

# resolve_and_pwd START —— 以 START 为起点、在「未显式提供 PROJECT_ROOT」前提下调用
# resolve_project_root；成功则在切换工作目录后输出最终目录（pwd），失败则由函数内
# exit 2 直接终止本（子）shell。供 `run resolve_and_pwd ...` 同时观察退出码与最终目录。
resolve_and_pwd() {
    local start="$1"
    PROJECT_ROOT=""
    resolve_project_root "$start"
    pwd
}

# ---------------------------------------------------------------------------
# 任务 3.2：属性测试 —— Property 3 项目根目录定位返回最近的有效祖先
# Feature: scheduled-csv-html-pipeline, Property 3: 对任意目录树，从给定起点向上查找，
# resolve_project_root 的结果应是从起点向上最近一个【同时】包含 gencsv/ 与 maps/ 的
# 祖先目录；不存在这样的祖先时判定为失败（exit 2）。
# Validates: Requirements 6.1
# ---------------------------------------------------------------------------
@test "Property 3: 根目录定位返回最近的有效祖先，否则失败（≥100 次迭代）" {
    local iterations=100 i
    for ((i = 0; i < iterations; i++)); do
        reset_root_state

        # 为本轮迭代准备独立的基目录，避免不同轮次的目录树相互干扰。
        local base="${TEST_WORKDIR}/tree_${i}"
        mkdir -p "$base"

        # 生成随机目录树：第 1 行为起点（最深一级），第 2 行为期望的有效祖先
        # （为空表示本轮未放置任何标记，应判定为失败）。
        local lines=()
        mapfile -t lines < <(make_random_project_tree "$base")
        local leaf="${lines[0]:-}"
        local expected="${lines[1]:-}"

        run resolve_and_pwd "$leaf"

        if [[ -n "$expected" ]]; then
            # 应成功并 cd 到期望的最近有效祖先。比较时对期望路径做同样的规范化
            # （cd && pwd），消除可能的路径表示差异。
            local expected_norm
            expected_norm="$(cd "$expected" && pwd)"
            [ "$status" -eq 0 ] || {
                echo "迭代 $i：期望成功但 status=$status" >&2
                echo "起点=$leaf 期望祖先=$expected" >&2
                echo "输出=$output" >&2
                return 1
            }
            [ "${lines[-1]}" = "$expected_norm" ] || {
                echo "迭代 $i：定位结果不等于最近有效祖先" >&2
                echo "起点=$leaf 期望=$expected_norm 实际=${lines[-1]}" >&2
                return 1
            }
        else
            # 不存在有效祖先 → 应以退出码 2 失败。
            [ "$status" -eq 2 ] || {
                echo "迭代 $i：期望失败(exit 2) 但 status=$status" >&2
                echo "起点=$leaf 输出=$output" >&2
                return 1
            }
        fi
    done
}

# ---------------------------------------------------------------------------
# 任务 3.3：边界/错误用例 —— 缺失子目录 → exit 2
# Validates: Requirements 6.3, 10.3
# ---------------------------------------------------------------------------

@test "边界: 目录树仅含 gencsv/（缺 maps/）→ exit 2" {
    reset_root_state
    local base="${TEST_WORKDIR}/only_gencsv"
    local leaf
    leaf="$(make_random_dir_chain "$base")"
    mkdir -p "${base}/gencsv" # 仅放置其一

    run resolve_and_pwd "$leaf"
    [ "$status" -eq 2 ]
}

@test "边界: 目录树仅含 maps/（缺 gencsv/）→ exit 2" {
    reset_root_state
    local base="${TEST_WORKDIR}/only_maps"
    local leaf
    leaf="$(make_random_dir_chain "$base")"
    mkdir -p "${base}/maps" # 仅放置其一

    run resolve_and_pwd "$leaf"
    [ "$status" -eq 2 ]
}

@test "边界: 目录树两个标记都没有 → exit 2 且错误提及未找到" {
    reset_root_state
    local base="${TEST_WORKDIR}/no_markers"
    local leaf
    leaf="$(make_random_dir_chain "$base")"

    run resolve_and_pwd "$leaf"
    [ "$status" -eq 2 ]
    [[ "$output" == *gencsv* && "$output" == *maps* ]]
}

# ---------------------------------------------------------------------------
# 补充：情形 A —— 配置显式提供 PROJECT_ROOT 时仅做校验（不向上查找）
# Validates: Requirements 6.1, 6.2, 6.3, 10.3
# ---------------------------------------------------------------------------

# resolve_with_explicit_root ROOT —— 以显式 PROJECT_ROOT 调用并在成功后输出最终目录。
resolve_with_explicit_root() {
    PROJECT_ROOT="$1"
    resolve_project_root
    pwd
}

@test "情形 A: 显式 PROJECT_ROOT 同时含 gencsv/ 与 maps/ → 成功并 cd 进入" {
    reset_root_state
    local root="${TEST_WORKDIR}/explicit_ok"
    place_project_markers "$root"

    local expected_norm
    expected_norm="$(cd "$root" && pwd)"

    run resolve_with_explicit_root "$root"
    [ "$status" -eq 0 ]
    [ "${lines[-1]}" = "$expected_norm" ]
}

@test "情形 A: 显式 PROJECT_ROOT 缺少子目录 → exit 2（不回退向上查找）" {
    reset_root_state
    # 构造一个「祖先含标记、但显式指定的子目录自身不含标记」的场景：
    # 若实现错误地向上查找，可能误判成功；正确实现应直接对显式目录校验并失败。
    local ancestor="${TEST_WORKDIR}/explicit_bad"
    place_project_markers "$ancestor"
    local child="${ancestor}/child"
    mkdir -p "$child"

    run resolve_with_explicit_root "$child"
    [ "$status" -eq 2 ]
    [[ "$output" == *PROJECT_ROOT* ]]
}

@test "情形 A: 显式 PROJECT_ROOT 成功后对 VENV_PATH/LOG_DIR/LOCK_FILE 做二次缺省兜底" {
    reset_root_state
    local root="${TEST_WORKDIR}/explicit_defaults"
    place_project_markers "$root"
    local root_norm
    root_norm="$(cd "$root" && pwd)"

    # 在子 shell 内调用，依次输出三项缺省值以便断言（用换行分隔）。
    run bash -c '
        set -u
        source "'"${PIPELINE_SCRIPT}"'"
        PROJECT_ROOT="'"$root"'"
        VENV_PATH=""; LOG_DIR=""; LOCK_FILE=""
        resolve_project_root
        printf "%s\n%s\n%s\n" "$VENV_PATH" "$LOG_DIR" "$LOCK_FILE"
    '
    [ "$status" -eq 0 ]
    [ "${lines[-3]}" = "${root_norm}/venv" ]
    [ "${lines[-2]}" = "${root_norm}/logs/pipeline" ]
    [ "${lines[-1]}" = "${root_norm}/run_pipeline.lock" ]
}
