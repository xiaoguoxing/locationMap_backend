# run_pipeline.sh 测试说明（bats-core）

本目录是 `run_pipeline.sh`（Pipeline_Script，流水线脚本）的测试脚手架，基于
**bats-core**（Bash Automated Testing System，bash 脚本的事实标准测试框架）。

## 目录内容

- `test_helper.bash` —— 共享测试辅助。提供四类能力：
  1. **受守卫保护地加载主脚本**：`load_pipeline_script` 以 `source` 方式载入
     `run_pipeline.sh` 的内部函数，但【不触发】`main` 命令分发（依赖主脚本末尾的
     `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]` 守卫），便于隔离调用纯逻辑函数。
  2. **临时工作目录管理**：`setup_test_workdir` / `teardown_test_workdir`，供
     bats 用例的 `setup` / `teardown` 调用，自动创建并清理 `TEST_WORKDIR`。
  3. **外部依赖打桩（stub）**：对 `python` / `python3` / `date` 等命令打桩
     （`make_command_stub`、`stub_date`），对虚拟环境 `activate` 打桩
     （`make_fake_venv`，可指定激活成功或失败），用于隔离副作用并记录调用参数。
  4. **轻量随机输入生成器**：`rand_exit_code`、`rand_config_subset`、
     `make_random_project_tree`、`rand_date_filename`、`rand_subcommand`、
     `rand_log_level` 等。属性测试以「在 bats 用例内用生成器循环驱动 ≥100 次迭代」
     的方式实现（bash 生态无通用属性测试库）。
- `run_static_checks.sh` —— 对 `run_pipeline.sh` 执行 `bash -n` 语法检查与可选的
  `shellcheck` 静态分析。
- `*.bats` —— 后续任务（2~11）将逐步添加的单元测试、属性测试与集成测试用例。

## 本地运行方式

测试由用户在终端**手动执行**（本自动化工作流不运行长任务，因属性测试循环迭代耗时较长）。

先安装 bats-core（任选其一）：

```bash
# Debian / Ubuntu / KylinOS（银河麒麟）
sudo apt-get install -y bats

# 或从源码安装
git clone https://github.com/bats-core/bats-core.git
cd bats-core && sudo ./install.sh /usr/local
```

然后在项目根目录运行全部测试：

```bash
bats test/
```

也可只运行单个文件：

```bash
bats test/load_config.bats
```

> 说明：生产 / 定时运行目标为 Linux（KylinOS）。Windows 仅作开发机；
> 在 Windows 上可借助 WSL 或 Git Bash 环境运行 bats，但建议在 Linux 上验证。

## 在 .bats 文件中使用辅助的范例

```bash
#!/usr/bin/env bats

load 'test_helper'

setup() {
    setup_test_workdir      # 准备本用例的临时工作目录 TEST_WORKDIR
    load_pipeline_script    # 载入被测函数（不触发 main 分发）
}

teardown() {
    teardown_test_workdir   # 清理临时工作目录与 PATH 打桩
}

@test "示例：随机驱动属性测试（≥100 次迭代）" {
    local i
    for ((i = 0; i < 100; i++)); do
        local c m
        c="$(rand_exit_code)"
        m="$(rand_exit_code)"
        # ……在此调用被测函数并断言属性成立……
    done
}
```
