---
name: hermes-purge
description: "Use when tune Hermes execution posture, purge rules, or restore them."
version: 1.0.0
metadata:
  hermes:
    tags: [purge, rules, autonomy, backup]
---

# hermes-purge（Hermes 版破甲层）

插件把「执行姿态」作为系统提示段注入每个新会话，规则是纯 markdown，可改可回滚。

## 什么时候用

- 用户说「你多做点 / 别老问我 / 一次做完」→ 先 `/purge doctor` 看注入层是否就绪，再决定改哪条规则。
- 用户要改行为规则 → 改 `$HERMES_HOME/purge/rules/*.md`（文件名排序拼接），不要改插件代码。
- 规则改坏了 → `/purge snapshots` 找 id，`/purge restore <id>`。

## 命令

| 命令 | 作用 |
|---|---|
| `/purge` / `/purge status` | 概览：开关、规则数、字符数、快照数、关键配置 |
| `/purge doctor` | 五层自检：插件 / 注入 / 生效 / 配置 / 备份 |
| `/purge on` `off` | 注入开关（新会话生效） |
| `/purge rules` | 规则文件清单 + sha256 |
| `/purge show` | 预览下次会话真正注入的文本 |
| `/purge apply` | 重新播种默认规则（不覆盖已有文件）+ 建快照 |
| `/purge snapshot [标签]` | 手动快照（sha256 清单） |
| `/purge restore <id>` | 回滚，回滚前自动再快照 |
| `/purge diff [id]` | 当前规则 vs 快照 |
| `hermes purge <同上>` | CLI 等价入口 |

## 硬约束

- 系统提示段上限 3900 字符，超了自动截断并在末尾标注。
- 每个新会话渲染一次；改完规则必须 `/new`，当前会话的提示已冻结（改它等于破坏 prompt cache）。
- 资金、隐私、破坏性操作和外部写入的确认要求写在 `10-boundaries.md` 里，删掉它等于放宽关键边界——不要为了「更顺」去改这一条。
- 数据目录：`$HERMES_HOME/purge/`（rules/、state.json、snapshots/）。卸载插件不会删它，规则仍保留。

## 桌面状态栏面板（源码保留，默认不安装）

- 用户在 2026-11-05 明确不要状态栏显示 purge 开关，`desktop-plugins/hermes-purge/` 已删除。源码仍在插件包的 `desktop-panel/plugin.js`，需要时 `cp` 到 `$HERMES_HOME/desktop-plugins/hermes-purge/plugin.js`（fs 监视热重载，无需重启）。
- **不要把它放进 `plugins/<pkg>/desktop/`**：Electron 会复制成包内「桌面半身」并盖 `.hermes-package.json`，带标记的桌面插件在 runtime-loader 里默认停用（opt-in），状态栏就没有 chip。表现是插件列表里能看到、可以手工开关，但默认不显示——写任何 Hermes 桌面插件都要记住这一条。
- 排查：`ls -a desktop-plugins/hermes-purge/` 见到 `.hermes-package.json` 就删；还不行把 `plugin.js` 移出再移回（逼 loader 丢弃旧 disk record）。
- 桌面插件不能写文件，所有读写走 `host.request(...)`/`ctx.storage`/`ctx.files`；面板读数只调 `cli.exec` 跑 `hermes purge status --json` 才和 CLI 同源。
