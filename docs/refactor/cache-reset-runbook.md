# Cache Reset Runbook

日期：2026-04-17

目的：

- 解决“改了代码但状态不干净”的排查成本
- 把可重建缓存、测试残留、解释器残留和真正代码问题区分开

当前仓库扫描结果：

- 已发现：
  - `.pytest_cache/`
  - `tests/__pycache__/`
  - `tests/contract/__pycache__/`
  - `wecom_ability_service/**/__pycache__/`
  - `docs/.DS_Store`
  - `.venv/`
  - `.venv311/`
- 当前扫描未发现：
  - 仓库内持久化 `*.sqlite` / `*.sqlite3` / `*.db` 文件

结论：

- 当前最常见的“脏状态”来源是 Python 字节码缓存、pytest cache、双解释器环境残留
- 尤其是当前仓库已经同时出现 Python 3.11 与 3.13 两套 `pyc`，最容易制造“同一段代码在不同解释器下表现不一样”的假象

## 1. 清理对象清单

| 清理对象 | 当前仓库是否存在 | 为什么会脏 | 何时需要清 | 是否安全删除 |
| --- | --- | --- | --- | --- |
| `**/__pycache__/` | 是 | Python 3.11 / 3.13 混用后，旧 `pyc` 容易制造错误定位偏差 | 切解释器、改 import 路径、删/改模块名后 | 是 |
| `*.pyc` / `*.pyo` | 是 | 与源码不一致时会表现为“像没更新代码” | 同上 | 是 |
| `.pytest_cache/` | 是 | 失败重跑、上次选择集、last failed 状态会误导本次结果 | pytest 行为异常、只跑到旧失败集、收集行为怪异时 | 是 |
| `.coverage` / `.coverage.*` / `htmlcov/` | 当前未扫到 | 旧覆盖率报告会让人误以为用例没更新 | 需要重新看覆盖率前 | 是 |
| `.mypy_cache/` / `.ruff_cache/` / `.hypothesis/` | 当前未扫到 | 静态检查或 property-based test 结果可能滞留 | lint / typecheck / hypothesis 异常时 | 是 |
| `docs/.DS_Store` | 是 | Finder 残留，会污染 `git status` | 文档目录出现无关变更时 | 是 |
| `.venv/` | 是 | Python 3.13 环境和当前通过的 3.11 环境并存，最容易造成解释器混淆 | requirements 改变、解释器切换、`ModuleNotFoundError` 指向标准库变化时 | 是，但默认不建议每次都删 |
| `.venv311/` | 是 | 与 `.venv/` 并存，命令如果没固定解释器会得到不同结果 | 同上 | 是，但默认不建议每次都删 |

## 2. 什么时候需要清

建议按下面顺序判断，而不是一上来就删环境：

1. 先清 `__pycache__`、`*.pyc`、`.pytest_cache`
2. 再重跑 Wave 1 最小冒烟集
3. 只有当错误仍然看起来和解释器 / 依赖版本相关时，再删除 `.venv` / `.venv311`

典型触发场景：

- 切换 Python 3.11 / 3.13 后，报错位置和 import 行为不一致
- 改了 import 路径、包边界、模块名，但运行结果像在走旧代码
- pytest 只重跑旧失败集，或者收集出的测试与预期不一致
- guardrail 明明已经改了，运行结果还像是旧规则
- shell 里 `python3`、`.venv/bin/python`、`.venv311/bin/python` 跑出来结果不同

## 3. 清理后的最小验证动作

最小验证只做 3 步：

1. 确认解释器

```bash
python3 --version
./.venv311/bin/python --version
```

2. 确认 pytest 可用解释器

```bash
./scripts/test_wave1_smoke.sh
```

3. 如果只想先看门禁是否干净

```bash
./.venv311/bin/python -m pytest -q tests/test_refactor_guardrails.py
```

## 4. 常见“像缓存问题，其实是代码问题”的识别方法

| 现象 | 更像缓存问题 | 更像代码问题 |
| --- | --- | --- |
| 同一测试在不同解释器下结果不一致 | 是，先看 `.venv` / `.venv311`、`pyc` | 也可能是版本兼容问题，需要查依赖与标准库差异 |
| 清掉 `__pycache__` 后问题立刻消失 | 是 | 否 |
| 清掉缓存后问题稳定复现 | 否 | 是 |
| 错误指向 `imghdr`、`distutils` 这类标准库兼容性 | 否，通常不是缓存 | 是，属于 Python 版本 / 代码兼容问题 |
| API 返回字段缺失、业务条件分支错走 | 否 | 是，优先查代码与 contract |
| 数据不一致只发生在切 DB / 初始化 schema 后 | 否 | 是，优先查 `db.py` / `schema*.sql` / 初始化逻辑 |
| 改了 controller，但页面仍然像旧逻辑 | 先看 `pyc` / 解释器 | 如果清理后仍复现，就是代码问题 |

## 5. 最小清理策略

默认建议：

- 只清缓存，不删环境

重置到“更干净但不重装依赖”的级别：

- 删除 `__pycache__`
- 删除 `*.pyc` / `*.pyo`
- 删除 `.pytest_cache`
- 删除 `.coverage*` / `htmlcov`
- 删除 `.DS_Store`

只有在下面情况才进入“重建环境”：

- 解释器版本切换
- requirements 改动
- 出现标准库兼容问题
- 一个环境稳定失败、另一个环境稳定通过

## 6. 推荐命令

标准清理：

```bash
./scripts/clean_dev_state.sh
```

只看会删什么：

```bash
./scripts/clean_dev_state.sh --dry-run
```

连本地虚拟环境一起删：

```bash
./scripts/clean_dev_state.sh --full
```

`--full` 只删除可重建环境，不删除真实业务数据，也不删除 git 跟踪文件。
