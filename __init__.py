"""hermes-purge —— Hermes 版 dsh-purge 设计移植。

把 dsh-purge 在 DeepSeek Harness 上做的事，用 Hermes 自己的插件 API 重做一遍：
  * 提示词注入  → ``register_system_prompt_section("purge.core")``（每个新会话冻结一次）
  * 规则管理    → ``$HERMES_HOME/purge/rules/*.md``，纯文本、可编辑、按文件名排序拼接
  * 状态自检    → ``/purge doctor`` 五层逐项判定（插件/注入/生效/配置/备份）
  * 备份回滚    → 每次写操作前自动快照，sha256 清单，``/purge restore <id>``
  * 不改宿主    → 没有 dsh 的 86 条宿主补丁，全部走公开插件 API

dsh-purge 里与 Hermes 无关的部分（asar 补丁、cordis 预设、拒答重试、steering 运行时）
在本机没有对应物：Hermes 本身不做拒答、已有 steering 与预设人格，故不移植。
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import purge_core, purge_commands

logger = logging.getLogger("hermes-purge")

_SKILL_DIR = Path(__file__).resolve().parent / "skills" / "hermes-purge"


def _register_skill(ctx) -> bool:
    """Registers the bundled how-to skill on runtimes that support it."""
    if not hasattr(ctx, "register_skill"):
        return False
    skill_md = _SKILL_DIR / "SKILL.md"
    if not skill_md.is_file():
        return False
    try:
        ctx.register_skill(
            "hermes-purge",
            skill_md,
            description="调 Hermes 执行姿态与规则层：/purge status|on|off|rules|restore。",
        )
        return True
    except Exception:
        logger.warning("hermes-purge: skill registration failed", exc_info=True)
        return False


def register(ctx) -> None:
    try:
        purge_core.ensure_layout()
    except Exception:
        logger.warning("hermes-purge: layout seed failed", exc_info=True)

    # 1) 提示词注入层：每个新会话渲染一次；/purge off 后返回空串即不注入。
    try:
        ctx.register_system_prompt_section(
            purge_core.SECTION_ID,
            purge_core.render_section,
            position="after_memory",
            max_chars=purge_core.SECTION_MAX_CHARS,
        )
        purge_core.SECTION_REGISTERED = True
    except Exception:
        logger.warning("hermes-purge: system prompt section registration failed", exc_info=True)

    # 2) 会话内命令 + CLI。
    ctx.register_command(
        "purge",
        handler=purge_commands.purge_command,
        description="Hermes 执行姿态层：状态自检 / 规则 / 开关 / 快照回滚",
        args_hint="[status|doctor|on|off|rules|show|apply|snapshot|snapshots|restore <id>|diff]",
    )
    ctx.register_cli_command(
        name="purge",
        help="Hermes 执行姿态层：状态自检 / 规则 / 开关 / 快照回滚",
        setup_fn=purge_commands.setup_argparse,
        handler_fn=purge_commands.handle_cli,
    )

    _register_skill(ctx)
    logger.info("hermes-purge registered (section=%s)", purge_core.SECTION_ID)
