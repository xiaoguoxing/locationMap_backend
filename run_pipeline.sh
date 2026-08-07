#!/bin/bash
#
# run_pipeline.sh —— 水质地图项目的定时自动化流水线编排脚本（Pipeline_Script）
#
# 作用：把当前在 Windows 上手动执行的两步流程串联为一条可被 cron / systemd timer
#       非交互调用的命令：
#         1) CSV_Step（CSV 生成步骤）：调用 gencsv/main.py 或 gencsv/date_range_runner.py
#         2) Map_Step（地图生成步骤）：调用 maps/location_mapper.py 与 maps/multi_param_mapper.py
#
# 用法：
#   ./run_pipeline.sh            # 运行完整流水线（CSV_Step -> Map_Step），无子命令等价于 run
#   ./run_pipeline.sh run        # 同上，显式运行
#   ./run_pipeline.sh status     # 查看是否有正在运行的实例（读取锁）
#   ./run_pipeline.sh --help     # 用法说明
#
# 风格约定（沿用 dashboard/manage.sh，对应需求 8.4）：
#   - #!/bin/bash 头部
#   - 后续步骤通过 source <venv>/bin/activate 激活虚拟环境
#   - case 命令分发
#   - 切入项目根目录失败即退出
#
# 注意：本脚本顶部设置 set -u（引用未定义变量即报错），但【不】全局开启 set -e；
#       而是对每个步骤显式判定退出码，以实现"CSV 失败则跳过 Map"的精确控制（需求 4）。
#
# 退出码约定（Exit_Code）：
#   0 全部成功 | 1 用法错误/非法配置 | 2 无法定位 Project_Root 或 cd 失败
#   3 虚拟环境激活失败 | 4 锁被运行中的实例持有 | 5 CSV_Step 失败 | 6 Map_Step 失败
#
# 本文件为任务 1 的【骨架】：仅搭建命令分发与各能力函数的占位结构。
# 后续任务将按设计文档把以下函数补全为完整实现：
#   - load_config        （任务 2：配置加载器）
#   - resolve_project_root（任务 3：工作目录定位器）
#   - activate_venv      （任务 4：虚拟环境激活器）
#   - log_line / cleanup_logs（任务 5：日志记录器与保留清理器）
#   - acquire_lock / release_lock（任务 6：运行锁管理器）
#   - run_step / run_pipeline（任务 7：步骤执行器与主编排流程）

set -u

# 被测脚本名（供用法信息显示；当被 source 加载用于测试时也安全）。
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"

# =============================================================================
# 配置加载器（Config Loader）—— 任务 2 实现
# 读取与脚本同目录或 PIPELINE_CONF 指定的 pipeline.conf，并为所有配置键提供缺省值。
# =============================================================================
load_config() {
    # ---- 1) 定位配置文件路径 ----------------------------------------------
    # 加载优先级：环境变量 PIPELINE_CONF 指定的路径 > 脚本同目录的 pipeline.conf。
    # 注：在函数内部 ${BASH_SOURCE[0]} 仍指向定义本函数的脚本文件（run_pipeline.sh），
    #     因此可据此解析出脚本所在的绝对目录。
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # ${PIPELINE_CONF:-...} 在 set -u 下安全：未设置时回退到同目录 pipeline.conf。
    local conf_file="${PIPELINE_CONF:-$script_dir/pipeline.conf}"

    # ---- 2) 加载配置文件（存在才 source，不存在则全部走缺省值，不报错）--------
    # pipeline.conf 是可被 source 的 shell 片段（KEY="value" 形式）。
    if [[ -f "$conf_file" ]]; then
        # shellcheck disable=SC1090
        source "$conf_file"
    fi

    # ---- 3) 为各配置键兜底缺省值（: "${KEY:=默认值}" 仅在未设置/为空时赋值）----
    # 独立缺省项（不依赖 PROJECT_ROOT）：
    : "${PROJECT_ROOT:=}"                                  # 空 → 触发后续自动向上定位
    : "${PYTHON_BIN:=python3}"                             # 回退用系统 Python 解释器
    : "${CSV_DATE_RANGE_ARGS:=--days 30 --range-days 7}"   # 透传给向前回看窗口模式的参数
    : "${LOG_RETENTION_DAYS:=7}"                           # 日志保留天数

    # 依赖 PROJECT_ROOT 的缺省项：VENV_PATH / LOG_DIR / LOCK_FILE。
    # 此阶段 PROJECT_ROOT 可能尚为空（需自动定位）。借助 ${PROJECT_ROOT:+...}：
    #   - PROJECT_ROOT 非空（用户显式提供）→ 当场用其拼出正确缺省路径；
    #   - PROJECT_ROOT 为空 → 展开为空串，这三项暂留空，待 resolve_project_root
    #     确定根目录后再做二次兜底（见任务 3）。
    : "${VENV_PATH:=${PROJECT_ROOT:+$PROJECT_ROOT/venv}}"
    : "${LOG_DIR:=${PROJECT_ROOT:+$PROJECT_ROOT/logs/pipeline}}"
    : "${LOCK_FILE:=${PROJECT_ROOT:+$PROJECT_ROOT/run_pipeline.lock}}"

    # ---- 4) 校验配置取值合法性（非法则记录 ERROR 并以退出码 1 结束）----------
    # 配置加载属于早期阶段，Run_Log 路径尚未确定（在任务 5 才生成），故此处除调用
    # log_line（待其实现后自动写入日志）外，同时回退输出到 stderr，确保错误可见。
    if ! [[ "$LOG_RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
        local msg="配置项 LOG_RETENTION_DAYS 非法：期望非负整数，实际为 '${LOG_RETENTION_DAYS}'"
        log_line ERROR "$msg"
        echo "[ERROR] $msg" >&2
        exit 1
    fi

    if [[ -z "$CSV_DATE_RANGE_ARGS" ]]; then
        local msg="配置项 CSV_DATE_RANGE_ARGS 非法：不能为空字符串"
        log_line ERROR "$msg"
        echo "[ERROR] $msg" >&2
        exit 1
    fi
}

# =============================================================================
# 工作目录定位器（Project_Root Resolver）—— 任务 3 实现
# 从脚本自身位置出发向上查找同时包含 gencsv/ 与 maps/ 的祖先目录，并切入该目录。
# =============================================================================
resolve_project_root() {
    # 起点目录：可显式传入一个起点目录（便于属性测试构造随机目录树后从此向上查找）；
    # 未传入时使用脚本自身所在目录。注意：在函数内部 ${BASH_SOURCE[0]} 仍指向定义本
    # 函数的脚本文件（run_pipeline.sh），故据此可解析脚本所在的绝对目录。
    local start_dir="${1:-}"

    # 读取配置阶段可能已显式提供的 PROJECT_ROOT。用 ${PROJECT_ROOT:-} 兜底，避免在
    # set -u 下（例如测试未先调用 load_config 就直接调用本函数）引用未定义变量而报错。
    local root="${PROJECT_ROOT:-}"

    # err 用于汇聚各失败点的错误消息，最后集中到统一错误分支处理（退出码 2）。
    local err=""

    if [[ -n "$root" ]]; then
        # ---- 情形 A：配置显式提供 PROJECT_ROOT —— 仅校验，不向上查找 ----
        # 校验该目录下是否【同时】存在 gencsv/ 与 maps/ 两个子目录。
        if [[ ! -d "$root/gencsv" || ! -d "$root/maps" ]]; then
            err="配置提供的 PROJECT_ROOT='${root}' 下未同时包含 gencsv/ 与 maps/ 子目录"
        fi
    else
        # ---- 情形 B：PROJECT_ROOT 为空 —— 从起点目录向上逐级自动查找 ----
        # 先把起点目录解析为绝对路径（cd 进去再 pwd），失败则记录错误。
        local origin=""
        if [[ -n "$start_dir" ]]; then
            origin="$(cd "$start_dir" 2>/dev/null && pwd)" || origin=""
            [[ -z "$origin" ]] && err="查找起点目录 '${1}' 不存在或不可访问"
        else
            origin="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || origin=""
            [[ -z "$origin" ]] && err="无法解析脚本所在目录以确定查找起点"
        fi

        # 仅在起点解析成功时才向上查找。
        if [[ -z "$err" ]]; then
            # 从起点向上逐级（dir -> dirname dir）查找最近一个同时含 gencsv/ 与 maps/
            # 的祖先目录；找到的第一个即为「最近」的有效祖先。
            local dir="$origin" parent found=""
            while :; do
                if [[ -d "$dir/gencsv" && -d "$dir/maps" ]]; then
                    found="$dir"
                    break
                fi
                parent="$(dirname "$dir")"
                # 到达文件系统根时 dirname 不再变化，停止以避免死循环。
                [[ "$parent" == "$dir" ]] && break
                dir="$parent"
            done

            if [[ -n "$found" ]]; then
                root="$found"
            else
                err="从 '${origin}' 向上未找到同时包含 gencsv/ 与 maps/ 的项目根目录"
            fi
        fi
    fi

    # ---- 切换工作目录到 Project_Root（需求 6.2），仅在前序步骤无错误时尝试 ----
    if [[ -z "$err" ]]; then
        cd "$root" 2>/dev/null || err="切换工作目录到 PROJECT_ROOT='${root}' 失败"
    fi

    # ---- 统一错误分支：记录 ERROR 后以退出码 2 结束（需求 6.3 / 10.3）----
    # 与 load_config 风格一致：除调用 log_line（待其实现后写入 Run_Log）外，同时回退
    # 输出到 stderr，确保在 Run_Log 尚未就绪的早期阶段错误仍可见。
    if [[ -n "$err" ]]; then
        log_line ERROR "$err"
        echo "[ERROR] $err" >&2
        exit 2
    fi

    # 统一以绝对路径记录最终的 PROJECT_ROOT（无论显式提供还是自动查找得来），
    # 确保后续依赖它拼出的缺省路径均为绝对路径。
    PROJECT_ROOT="$(pwd)"

    # ---- 二次缺省兜底：仅当这三项仍为空时，用已确定的 PROJECT_ROOT 拼出缺省路径 ----
    # 这三项在 load_config 阶段若 PROJECT_ROOT 尚为空会留空，故在此二次兜底。
    # 缺省值与 load_config / design.md 的 Config_File 表保持一致。
    : "${VENV_PATH:=$PROJECT_ROOT/venv}"
    : "${LOG_DIR:=$PROJECT_ROOT/logs/pipeline}"
    : "${LOCK_FILE:=$PROJECT_ROOT/run_pipeline.lock}"
}

# =============================================================================
# 虚拟环境激活器（Venv Activator）—— 任务 4 实现
# 在执行任何 Python 程序前激活项目 venv（cron 最小环境下也能加载依赖）。
# =============================================================================
activate_venv() {
    # 取配置阶段确定的 VENV_PATH 与 PYTHON_BIN；统一用 ${VAR:-} 兜底，避免在 set -u 下
    # （例如测试未先调用 load_config 就直接调用本函数）引用未定义变量而报错。
    local venv_path="${VENV_PATH:-}"
    local python_bin="${PYTHON_BIN:-python3}"

    if [[ -n "$venv_path" ]]; then
        # ---- 情形 A：VENV_PATH 非空 —— 激活项目虚拟环境（需求 7.1）----
        # source <venv>/bin/activate 会在当前 shell 注入虚拟环境的 PATH 等变量；
        # 若 activate 脚本不存在、或其自身以非零返回，则 source 返回非零，视为激活失败。
        # shellcheck disable=SC1090
        if ! source "$venv_path/bin/activate"; then
            # 与 load_config / resolve_project_root 风格一致：除调用 log_line（待其实现后
            # 写入 Run_Log）外，同时回退输出到 stderr，确保错误在早期阶段仍可见。
            local msg="虚拟环境激活失败：source '${venv_path}/bin/activate' 返回非零（需求 7.3）"
            log_line ERROR "$msg"
            echo "[ERROR] $msg" >&2
            exit 3
        fi
        # 激活成功后，后续步骤统一通过虚拟环境提供的 python 解释器调用（需求 7.1）。
        PYTHON="python"
    else
        # ---- 情形 B：VENV_PATH 为空 —— 回退系统 Python 解释器，不视为错误（需求 7.2）----
        # 后续步骤统一改用 $PYTHON_BIN 指定的系统解释器调用。
        PYTHON="$python_bin"
    fi
}

# =============================================================================
# 日志记录器与保留清理器（Logger + Retention Cleaner）—— 任务 5 实现
# 行格式 [YYYY-MM-DD HH:MM:SS] LEVEL message；按文件名内嵌日期清理过期日志。
# =============================================================================
log_line() {
    # TODO(任务 5.1): 追加一条带秒级时间戳的日志记录到 Run_Log。
    :
}

cleanup_logs() {
    # TODO(任务 5.3): 基于 pipeline_YYYYMMDD_HHMMSS.log 内嵌日期按保留天数清理。
    :
}

# =============================================================================
# 运行锁管理器（Lock Manager）—— 任务 6 实现
# 基于锁文件 + PID 存活检测防止重叠运行；含失效锁自愈。
# =============================================================================
acquire_lock() {
    # TODO(任务 6.1): 锁不存在则写入 $$ 获取；存活 PID 持有则退出码 4；失效锁清除后重试。
    :
}

release_lock() {
    # TODO(任务 6.1): 仅在自己持有时删除锁文件（由 trap ... EXIT 调用）。
    :
}

# =============================================================================
# 步骤执行器（Step Runner）—— 任务 7 实现
# 以 cmd 2>&1 | tee -a 捕获输出进日志，用 ${PIPESTATUS[0]} 取真实退出码。
# =============================================================================
run_step() {
    # TODO(任务 7.1): 执行命令、捕获 stdout/stderr 进 Run_Log，返回该步骤退出码。
    :
}

# =============================================================================
# 主编排流程（Main Orchestration）—— 任务 7.2 实现
# 串接：加载配置 -> 定位并 cd 根目录 -> 获取锁 -> 激活 venv -> CSV_Step -> Map_Step -> 清理与结束。
# =============================================================================
run_pipeline() {
    # TODO(任务 8.2): CSV_Step 固定以向前回看窗口模式调用 date_range_runner.py，
    #                 随后固定执行 Map_Step 两个程序，并按退出码聚合规则汇总整体结果
    #                 （退出码 5 / 6 / 0）。
    echo "TODO: 完整流水线尚未实现（待任务 2-7 完成后接线）。"
}

# =============================================================================
# status 子命令 —— 任务 6 实现
# 读取锁文件，报告是否存在正在运行的实例。
# =============================================================================
cmd_status() {
    # TODO(任务 6): 读取 LOCK_FILE 并通过 kill -0 检测持有进程，报告运行状态。
    echo "TODO: 运行状态查询尚未实现（待任务 6 完成）。"
}

# =============================================================================
# 用法说明
# =============================================================================
usage() {
    cat <<EOF
用法: ./${SCRIPT_NAME} [命令]

命令:
  run        运行完整流水线（CSV_Step -> Map_Step）。无命令时默认执行 run。
  status     查看是否有正在运行的流水线实例（读取锁文件）。
  --help     显示本用法说明。

示例:
  ./${SCRIPT_NAME}            # 运行完整流水线
  ./${SCRIPT_NAME} run        # 显式运行完整流水线
  ./${SCRIPT_NAME} status     # 查看运行状态
EOF
}

# =============================================================================
# 命令分发（Entry & Dispatch）
# 沿用 manage.sh 的 case 风格；无任何子命令时等价于 run（满足需求 7.1 的非交互调用）。
# =============================================================================
main() {
    local command="${1:-run}"

    case "$command" in
        run)
            run_pipeline
            ;;
        status)
            cmd_status
            ;;
        --help | -h | help)
            usage
            ;;
        *)
            echo "未知命令: ${command}" >&2
            usage >&2
            exit 1
            ;;
    esac
}

# 仅当脚本被【直接执行】（而非被测试 source 加载）时才运行命令分发。
# 这样 test/test_helper.bash 可以 source 本脚本以单独访问内部函数，
# 而不会触发 main 分发——这是后续任务单元/属性测试隔离纯逻辑的关键。
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
