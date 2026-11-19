# hermes-purge 1.2.0

**[中文](#中文) · [English](#english)**

> Hermes Agent 执行姿态控制层：把「什么时候自己做完、什么时候必须停下来问」写成纯 markdown 规则，作为插件提示段注入每个新会话 —— 可开关、可快照、可回滚，不改宿主代码。
>
> An execution-posture layer for Hermes Agent: it injects a small set of plain-markdown rules into every new session through a plugin prompt section — switchable, snapshot-able, revertible, with no host patching.

---

## 中文

### 它是什么

Hermes 默认的执行节奏容易落到两个极端：要么每一步都停下来问「要不要继续」，要么闷头做完、连花钱和删数据都不打招呼。这个插件在**每个新会话开始时**注入一段约 1.2k 字符的系统提示，把节奏和边界说清楚。

- 插件本体只有四个文件，无第三方 Python 依赖，不联网、无遥测。
- 规则是纯 markdown，放在 `$HERMES_HOME/purge/rules/*.md`，按文件名排序拼接。改规则不需要改代码。
- 任何写操作前自动打快照（sha256 清单），回滚本身也可回滚。
- 一条命令开关：`/purge off` 之后新会话不再注入，旧会话不受影响。

### 它解开什么，不解开什么

它管的只有**交互层**的行为，一处都不碰**内容层**的拒答。这是设计边界，不是能力不足。

| 限制 | 本插件 | 说明 |
|---|---|---|
| 每步都要确认「要不要继续」 | ✅ 收紧流程 | 规则 1/3：一轮做完，只在方向真分叉、涉资金、不可逆三种情况停 |
| 交半成品、以「接下来我会…」结尾 | ✅ 收紧流程 | 规则 2：要么给真实输出，要么给明确阻塞点和替代路径 |
| 笼统报失败后干等 | ✅ 收紧流程 | 规则 4：换工具/接口再试一次，报阻塞必须带错误原文 |
| 外部写入后不核对 | ✅ 收紧流程 | 规则 5：回读哈希、回执、进程状态再报完成 |
| 内容层安全拒答（某些话题模型直接不答） | ❌ 不能 | 权重级对齐，system prompt 改不动；本包无拒答重试钩子 |
| Hermes 命令审批 / 沙箱 / 密钥脱敏 | ❌ 不能 | 宿主层机制；代码只读 `approvals.mode` 用于自检展示 |
| 修改 `config.yaml` / `SOUL.md` / 宿主源码 | ❌ 不做 | 只注册提示段、命令、CLI 命令、技能四个表面 |

规则文件分两块：`00-execution.md` 管怎么干活，`10-boundaries.md` 管哪里必须停。分开写是为了不让人为了「更顺」顺手把安全边界一起删掉。

### 目录结构

```
plugin.yaml              # 清单：name/version/requires_hermes >=0.22.0
__init__.py              # register(ctx)：注入段 + /purge 命令 + hermes purge + 技能
purge_core.py            # 路径、状态、规则拼接、快照回滚、五层自检
purge_commands.py        # /purge 与 hermes purge 的实现
rules/00-execution.md    # 执行姿态规则（打包默认值）
rules/10-boundaries.md   # 边界规则（打包默认值）
skills/hermes-purge/     # 由插件注册的技能（用法速查）
desktop-panel/plugin.js  # 可选桌面状态面板源码，不自动安装
install.sh / install.ps1 # 复制到持久源码目录 → validate → install --enable
```

### 安装

仓库根目录就是插件根目录。先读一遍 `rules/` 下两个文件，那是会注入到你每个新会话里的文本。

**方式一：用安装脚本（已验证路径）**

```bash
# Git Bash / macOS / Linux
bash ./install.sh
```

```powershell
# Windows PowerShell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

脚本会：复制到 `$HERMES_HOME/src/hermes-purge-export-1.2.0` → 建本地 git 提交（Hermes 的 `file://` 安装要求目标是 git 仓库）→ `hermes plugins validate` → `hermes plugins install ... --enable` → `hermes plugins doctor --ci`。
如果 `$HERMES_HOME/plugins/hermes-purge` 已存在，脚本**直接停止**，不会覆盖你正在用的插件。

**方式二：从 GitHub 仓库安装**

```bash
git clone https://github.com/ifascloud/hermes-purge-1.2.0.git
hermes plugins install "file:///<absolute-path-to-clone>" --enable
```

**方式三：手工复制（自己掌控每一步）**

```bash
cp -R . "$HERMES_HOME/src/hermes-purge"
cd "$HERMES_HOME/src/hermes-purge" && git init -q && git add -A && git commit -qm "v1.2.0"
hermes plugins validate "$HERMES_HOME/src/hermes-purge"
hermes plugins install "file://$HERMES_HOME/src/hermes-purge" --enable
```

安装后**必须 `/new` 开新会话**：提示段在会话开始就冻结，当前会话读不到新规则。

### 命令

会话内 `/purge ...`，终端 `hermes purge ...`，两者同源。

| 命令 | 作用 |
|---|---|
| `/purge` / `/purge status` | 概览：开关、规则数、字符数、快照数 |
| `/purge doctor` | 五层自检：插件 / 注入 / 生效 / 配置 / 备份 |
| `/purge rules` | 规则文件清单 + sha256 |
| `/purge show` | 预览下次会话真正注入的文本 |
| `/purge on` / `off` | 注入开关（新会话生效） |
| `/purge apply` | 重新播种默认规则（已存在的文件不覆盖） |
| `/purge snapshot [标签]` | 手动快照 |
| `/purge snapshots` | 快照列表 |
| `/purge restore <id>` | 回滚（回滚前自动再快照一次） |
| `/purge diff [id]` | 当前规则 vs 快照 |
| `/purge status --json` | 机器可读状态（桌面面板走这个） |

### 改规则

改 `$HERMES_HOME/purge/rules/*.md`，不要改插件代码。加文件就用数字前缀控制顺序（`20-xxx.md` 排在 `10-boundaries.md` 之后）。

- **播种不覆盖**：插件首次加载只补缺失文件，你改过的规则不会被包内默认值冲掉 —— 所以换机器搬这个包，本机规则是安全的。
- **改完必须 `/new`**：当前会话的提示已冻结，改它等于破坏 prompt cache。
- **改坏了**：`/purge snapshots` 找 id，`/purge restore <id>`；回滚前会再打一个 pre-restore 快照，回滚也可回滚。

### 验收

| 检查 | 期望 |
|---|---|
| `hermes plugins validate <dir> --json` | `"ok": true`，`security scan: safe` |
| `hermes plugins doctor <dir> --ci` | 运行时导入与注册通过 |
| `/purge status` | 注入：开 · 规则 N 条 · 字符数 < 3900 |
| `/new` 后 `/purge show` | 看到完整规则文本（含头尾标记） |
| `/purge doctor` | 五层全 ✓，结论「就绪」 |

### 上限与已知限制

- **3900 字符预算**（`SECTION_MAX_CHARS = 3900`，含头尾标记）。超了自动截断并在末尾标注，不会静默丢规则。
- **注入位置只有 `after_memory`**：Hermes 仅提供这一个位置，插件无法选择更靠前的位置。
- **每会话冻结一次**：不重启会话就无法让新规则进入当前上下文。
- **配置读数是只读的**：`/purge doctor` 里的 `max_turns` / `approvals` / `model` 来自**接收机器自己的** `config.yaml`，换台机器数字不同是正常的，不是移植失败。
- **桌面面板是 opt-in**：`desktop-panel/plugin.js` 需要手动 `cp` 到 `$HERMES_HOME/desktop-plugins/hermes-purge/plugin.js`。别放进 `plugins/<pkg>/desktop/` —— Electron 会当成包内桌面半身并默认停用，状态栏就没有 chip。

### 卸载

```bash
hermes plugins disable hermes-purge     # 只是关掉
hermes plugins remove  hermes-purge     # 移除插件
```

**卸载不会删数据目录** `$HERMES_HOME/purge/` —— 你写的规则、状态、快照都还在。要清干净就自己删那个目录，删之前想清楚快照也在里面。

### 隐私与来源

- 包内不含凭据、令牌、私钥、钱包地址、本机绝对路径，也不含 `state.json` / 快照 / `config.yaml`。
- 设计参考 dsh-purge（DeepSeek Harness 的同类插件）；Hermes 版是机制重写而非代码复制：走 `system_prompt_section` 官方通道，不做 asar/源码补丁，也不移植拒答重试与人格预设。
- 许可证：MIT。

---

## English

### What it is

Hermes' default pacing tends to drift to one of two extremes: asking permission before every step, or plowing through a task without a word about spending money or deleting data. This plugin injects ~1.2k characters of system prompt at the **start of every new session** to pin down both the pace and the boundaries.

- Four source files, no third-party Python dependencies, no network calls, no telemetry.
- Rules are plain markdown in `$HERMES_HOME/purge/rules/*.md`, concatenated in filename order. Editing rules never means editing code.
- Every mutation snapshots first (sha256 manifest), and a restore is itself reversible.
- One switch: `/purge off`, and new sessions stop injecting. Running sessions are untouched.

### What it loosens — and what it does not

It only touches **interaction-layer** behavior. It does not touch **content-layer** refusals at all. That is a design boundary, not a missing feature.

| Constraint | This plugin | Notes |
|---|---|---|
| Asking "shall I continue?" at every step | ✅ tightens the flow | Rule 1/3: finish in one pass; stop only on a real fork, money, or an irreversible action |
| Half-finished work ending in "next I will…" | ✅ tightens the flow | Rule 2: real output, or an explicit blocker with alternatives |
| Vague "it failed" followed by silence | ✅ tightens the flow | Rule 4: retry with a different tool/interface, then report the actual error text |
| Reporting success without reading back | ✅ tightens the flow | Rule 5: verify hashes, receipts, process state before claiming done |
| Content-layer safety refusals | ❌ cannot | Weights-level alignment; no refusal-retry hook ships here |
| Hermes approvals / sandbox / secret redaction | ❌ cannot | Host-level; the code only *reads* `approvals.mode` for the self-check |
| Editing `config.yaml` / `SOUL.md` / host source | ❌ does not | Registers exactly four surfaces: prompt section, command, CLI command, skill |

The rules split in two on purpose: `00-execution.md` covers how to work, `10-boundaries.md` covers where to stop. Separate files so nobody deletes the safety half while chasing a smoother flow.

### Layout

```
plugin.yaml              # manifest: name/version/requires_hermes >=0.22.0
__init__.py              # register(ctx): section + /purge + hermes purge + skill
purge_core.py            # paths, state, rule composition, snapshots, five-layer check
purge_commands.py        # implementations of /purge and hermes purge
rules/00-execution.md    # execution-posture rules (packaged defaults)
rules/10-boundaries.md   # boundary rules (packaged defaults)
skills/hermes-purge/     # skill registered by the plugin (quick reference)
desktop-panel/plugin.js  # optional desktop status panel source, not auto-installed
install.sh / install.ps1 # copy to a durable source dir → validate → install --enable
```

### Install

The repository root **is** the plugin root. Read the two files in `rules/` first — that is the text that will be injected into every new session.

**Option 1: installers (verified path)**

```bash
# Git Bash / macOS / Linux
bash ./install.sh
```

```powershell
# Windows PowerShell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Each installer copies the package to `$HERMES_HOME/src/hermes-purge-export-1.2.0`, makes a local git commit (Hermes `file://` installs clone a git URL), runs `hermes plugins validate`, then `hermes plugins install ... --enable`, then `hermes plugins doctor --ci`. If `$HERMES_HOME/plugins/hermes-purge` already exists it **stops without changing anything** rather than overwriting the plugin you are running.

**Option 2: from the GitHub repo**

```bash
git clone https://github.com/ifascloud/hermes-purge-1.2.0.git
hermes plugins install "file:///<absolute-path-to-clone>" --enable
```

**Option 3: manual, step by step**

```bash
cp -R . "$HERMES_HOME/src/hermes-purge"
cd "$HERMES_HOME/src/hermes-purge" && git init -q && git add -A && git commit -qm "v1.2.0"
hermes plugins validate "$HERMES_HOME/src/hermes-purge"
hermes plugins install "file://$HERMES_HOME/src/hermes-purge" --enable
```

After installing you **must start a new session (`/new`)**: the prompt section is frozen at session start, so the running session will not see the new rules.

### Commands

`/purge ...` in chat, `hermes purge ...` in a terminal — same implementation.

| Command | Purpose |
|---|---|
| `/purge` / `/purge status` | Overview: toggle, rule count, char count, snapshots |
| `/purge doctor` | Five-layer self-check: plugin / injection / registration / config / backups |
| `/purge rules` | Rule files with sha256 |
| `/purge show` | Preview the exact text the next session will inject |
| `/purge on` / `off` | Injection toggle (applies to new sessions) |
| `/purge apply` | Re-seed packaged defaults (never overwrites existing files) |
| `/purge snapshot [label]` | Manual snapshot |
| `/purge snapshots` | List snapshots |
| `/purge restore <id>` | Restore; snapshots the current state first |
| `/purge diff [id]` | Live rules vs a snapshot |
| `/purge status --json` | Machine-readable status (used by the desktop panel) |

### Editing rules

Edit `$HERMES_HOME/purge/rules/*.md`, never the plugin code. Add files with numeric prefixes to control order (`20-xxx.md` sorts after `10-boundaries.md`).

- **Seeding never overwrites**: first load only fills in missing files, so your edited rules survive shipping the package to another machine.
- **`/new` is mandatory afterwards**: the current session's prompt is frozen; editing it would break prompt caching.
- **If you break something**: `/purge snapshots` for an id, then `/purge restore <id>`. A pre-restore snapshot is taken automatically, so the rollback itself is reversible.

### Acceptance checks

| Check | Expected |
|---|---|
| `hermes plugins validate <dir> --json` | `"ok": true`, `security scan: safe` |
| `hermes plugins doctor <dir> --ci` | Runtime import and registration pass |
| `/purge status` | Injection on · N rules · under 3900 chars |
| `/purge show` after `/new` | Full rule text including header/footer markers |
| `/purge doctor` | All five layers ✓, verdict "ready" |

### Limits and known constraints

- **3900-character budget** (`SECTION_MAX_CHARS = 3900`, markers included). Overflow is truncated with an explicit marker at the end — rules are never silently dropped.
- **`after_memory` is the only injection position** Hermes offers; the plugin cannot place itself earlier.
- **Frozen once per session**: new rules cannot enter the current context without a new session.
- **Config readouts are read-only**: `max_turns` / `approvals` / `model` in `/purge doctor` come from the **receiving machine's own** `config.yaml`. Different numbers there are expected, not a failed port.
- **Desktop panel is opt-in**: copy `desktop-panel/plugin.js` to `$HERMES_HOME/desktop-plugins/hermes-purge/plugin.js` yourself. Do not place it under `plugins/<pkg>/desktop/` — Electron copies it into the package as a "desktop half" and disables it by default, leaving no status-bar chip.

### Uninstall

```bash
hermes plugins disable hermes-purge     # turn it off
hermes plugins remove  hermes-purge     # remove the plugin
```

**Uninstalling does not delete the data directory** `$HERMES_HOME/purge/` — your rules, state and snapshots stay put. Delete it yourself if you want a clean slate, remembering the snapshots live in there too.

### Privacy and provenance

- No credentials, tokens, private keys, wallet addresses, or machine-specific absolute paths. No `state.json`, snapshots, or `config.yaml`.
- Design draws on dsh-purge (a sibling plugin for DeepSeek Harness); the Hermes version is a mechanism rewrite, not a code copy — it uses the official `system_prompt_section` channel, performs no asar/source patching, and deliberately does not port refusal-retry or persona presets.
- License: MIT.