# 本地 Skill 打包说明

## 一句话先说清

现在 `partner_search` 和 `persona_memory_sync` 不应该再靠“运行时临时塞路径”才能用，而应该像正常 Python 包一样被安装进环境。

这样做的目的很简单：

- 本地开发和线上运行用的是同一套装法
- `recommendation_system`、`matchmaking_system`、`gateway` 这些系统直接 `import partner_search` 就能跑
- `partner-search`、`persona-memory-sync` 两个命令行脚本会稳定出现在虚拟环境里

## 你可以把它理解成什么

以前更像：

- 代码在仓库里
- 启动时偷偷把某个目录塞进 `sys.path`
- 所以“当前这次能跑”，但换个机器、换个进程、换个部署脚本就容易出问题

现在更像：

- 先把项目安装进 Python 环境
- 这个环境里明确有 `her` 这个包
- `partner_search` 和 `persona_memory_sync` 都是这个包的一部分
- 谁来启动都按同一套规则找代码

## 第一次在开发机上怎么装

前提：

- Python 版本必须是 `>= 3.10`
- 推荐直接用 `python3.12`

最简单的方式：

```bash
scripts/dev_setup.sh --python python3.12
```

这个脚本会做三件事：

1. 创建 `.venv`
2. 把当前项目以 editable 方式装进去
3. 顺手跑一遍打包自检

装完以后启用环境：

```bash
source .venv/bin/activate
```

## 日常开发时怎么判断自己没搞坏

改了 `partner_search/`、`persona_memory_sync/`、`pyproject.toml`、`setup.py` 这些地方后，至少跑下面几步：

```bash
python scripts/check_skill_packaging.py
python -m pytest tests/test_skill_packaging.py -q
```

如果你改的是发布入口，或者想确认命令行脚本也没坏，再多跑一步：

```bash
python scripts/check_skill_packaging.py --require-console-scripts
```

## 上线前怎么验

最稳的方式不是“我感觉能 import”，而是按上线环境再装一次，然后检查脚本和依赖是不是都在。

推荐直接跑：

```bash
scripts/release_check.sh --python .venv/bin/python
```

这个脚本会检查：

- 当前环境里是否真的安装了 `her`
- `partner-search` 和 `persona-memory-sync` 是否真的存在
- 这两个脚本是不是由 `her` 这个 distribution 提供
- 主系统是否还能正常导入这些 skill 包
- 关键测试是否还能通过

## 看到什么结果，才算真的成功

成功不是“本地某个模块 import 过一次”，而是下面这些条件同时成立：

- `scripts/check_skill_packaging.py --require-console-scripts` 返回成功
- 输出里 `distribution.installed = true`
- 输出里两个 `console_scripts` 都是 `installed = true`
- 输出里两个 `console_scripts` 的 `provider` 都是 `her`
- `.venv/bin/partner-search --help` 能跑
- `.venv/bin/persona-memory-sync --help` 能跑

## 为什么现在仓库里同时有 `pyproject.toml` 和 `setup.py`

可以把它理解成：

- `pyproject.toml` 是现代标准配置
- `setup.py` 是兼容层

补这个兼容层的原因很实际：

- 新环境会优先按 `pyproject.toml` 走
- 但有些老一点的 editable install 路径，还是会退回到 `setup.py develop`
- 如果没有这个兼容层，就可能出现：
  - `her` 能部分识别
  - 但两个 console script 没有真正装出来
  - 或者安装结果变成 `UNKNOWN`

所以现在保留 `setup.py`，不是倒退，而是为了让不同安装路径都稳定。

## 常见报错怎么理解

### 1. `ModuleNotFoundError: partner_search`

大白话：

- 你现在用的这个 Python 环境里，项目根本没装进去

先做：

```bash
scripts/dev_setup.sh --python python3.12
```

或者确认你现在是不是已经切到正确的 `.venv`。

### 2. `console_scripts.installed = false`

大白话：

- 包也许装了
- 但命令行入口没装进去

优先排查：

- 你跑检查时用的 Python，和你安装时用的 Python，是不是同一个
- 当前环境里是不是完整安装了 `her`
- 有没有跳过安装步骤，直接在源码目录里运行脚本

### 3. `requires a different Python: 3.9 ... not in '>=3.10'`

大白话：

- 不是项目坏了
- 是解释器版本不符合要求

处理方式：

- 换到 `python3.10`、`python3.11` 或 `python3.12`

### 4. 离线环境里 `pip` 拉不到 `setuptools` / `wheel`

大白话：

- 不是业务代码错了
- 是构建工具没准备好

处理方式：

- 先准备好可用的 Python 打包工具
- 再执行安装
- 如果是完全离线部署，部署镜像里要提前带上这些基础构建依赖

## 团队以后改这块时的规则

- 改公共 API：同时看 `partner_search/__init__.py` 或 `persona_memory_sync/__init__.py`
- 改命令行入口：同时看 `pyproject.toml` 和 `setup.py`
- 改打包布局：必须跑 `tests/test_skill_packaging.py`
- 改上线流程：必须跑 `scripts/release_check.sh`

## 最后用一句大白话总结

这套机制要解决的不是“让本地这一次跑起来”，而是“让任何机器、任何环境、任何启动方式都按同一套规则把 skill 找到并跑起来”。
