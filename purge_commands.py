"""hermes-purge 的命令面：``/purge`` 会话内命令 + ``hermes purge`` CLI。

两个入口共用同一批函数，参数语法一致：
    status            概览（默认）
    doctor            五层自检
    on / off          注入开关（下次新会话生效）
    rules             规则文件清单（大小 / sha256 前 12 位）
    show              预览下次会话真正注入的文本
    apply             重新播种默认规则 + 建基线快照
    snapshot [标签]   手动快照
    snapshots         快照列表
    restore <id>      回滚（回滚前自动再快照一次）
    diff [id]         当前规则与快照的差异
"""

from __future__ import annotations

from typing import Any, Optional

from . import purge_core as core

HELP = (
    "**/purge —— Hermes 执行姿态层**\n"
    "status · doctor · on · off · rules · show · apply · snapshot [标签] · snapshots · restore <id> · diff [id]\n"
    "规则文件：{rules_dir}\n"
    "注入段：{section}（after_memory，≤{limit} 字符，每个新会话渲染一次）"
)


def _help() -> str:
    return HELP.format(
        rules_dir=core.rules_dir(),
        section=core.SECTION_ID,
        limit=core.SECTION_MAX_CHARS,
    )


def _status() -> str:
    state = core.read_state()
    rules = core.list_rules()
    body = core.compose_rules()
    snaps = core.list_snapshots()
    conf = core.config_summary()
    on = "开" if state.get("enabled", True) else "关"
    lines = [
        "**purge 状态**",
        f"注入：{on} · 规则 {len(rules)} 条 / {len(body)} 字符（上限 {core.SECTION_MAX_CHARS}）",
        f"快照：{len(snaps)} 个" + (f" · 最新 {snaps[0]['id']}" if snaps else "（尚无）"),
        f"配置：max_turns={conf['max_turns']} · approvals={conf['approval_mode']} · model={conf['default_model']}",
        f"目录：{core.data_dir()}",
        "生效范围：新会话；当前会话的系统提示已冻结，改规则后 /new 才看得到",
    ]
    return "\n".join(lines)


def _rules() -> str:
    rules = core.list_rules()
    if not rules:
        return "规则目录为空。执行 /purge apply 播种默认规则。"
    lines = [f"**规则文件**（{core.rules_dir()}）"]
    total = 0
    for path in rules:
        size = path.stat().st_size
        total += size
        lines.append(f"- {path.name} · {size} B · {core.sha256_file(path)[:12]}")
    lines.append(f"\n合计 {len(rules)} 个文件 / {total} B；拼接后 {len(core.compose_rules())} 字符，上限 {core.SECTION_MAX_CHARS}")
    return "\n".join(lines)


def _show() -> str:
    text = core.render_section({})
    if not text:
        return "当前不会注入任何内容（已关闭或规则为空）。"
    return f"**下次新会话将注入以下文本**（{len(text)} 字符）\n\n```markdown\n{text}\n```"


def _apply() -> str:
    pre = core.snapshot("pre-apply")
    seeded = core.ensure_layout()
    post = core.snapshot("apply")
    lines = ["**purge apply 完成**"]
    if seeded.get("seeded"):
        lines.append(f"播种默认规则：{', '.join(seeded['seeded'])}")
    else:
        lines.append("规则已存在，未覆盖（保护手改内容）")
    lines.append(f"注入开关：{'开' if core.read_state().get('enabled', True) else '关'}")
    lines.append(f"快照：{pre['id']} → {post['id']}")
    lines.append("生效：下一个新会话（/new）")
    return "\n".join(lines)


def _snapshot(label: str) -> str:
    manifest = core.snapshot(label or "manual")
    return f"快照已建：{manifest['id']} · {len(manifest['files'])} 个文件 · sha256 校验通过"


def _snapshots() -> str:
    snaps = core.list_snapshots()
    if not snaps:
        return "还没有快照。"
    lines = ["**快照列表**（新 → 旧）"]
    for item in snaps[:20]:
        ok, _bad = core.verify_snapshot(item["id"])
        lines.append(f"- {item['id']} · {item['files']} 文件 · {'✓ 完整' if ok else '✗ 损坏'}")
    if len(snaps) > 20:
        lines.append(f"… 共 {len(snaps)} 个")
    return "\n".join(lines)


def _restore(snap_id: str) -> str:
    if not snap_id:
        return "用法：/purge restore <快照id>（/purge snapshots 查看）"
    try:
        result = core.restore(snap_id)
    except FileNotFoundError:
        return f"找不到快照 {snap_id}"
    except Exception as exc:
        return f"回滚失败：{exc}"
    tail = "哈希全部复核一致" if not result["mismatched"] else f"复核不符：{result['mismatched']}"
    return (
        f"已回滚到 {snap_id}：{', '.join(result['restored']) or '无文件'} · {tail}\n"
        f"回滚前现场另存为 {result['pre_restore_snapshot']}；新会话生效"
    )


def _diff(snap_ref: str) -> str:
    snaps = core.list_snapshots()
    if not snaps:
        return "没有可对比的快照。"
    # 默认对着最近一次「非回滚现场」的快照比，回滚后看到的差异才有意义。
    if not snap_ref:
        stable = [s for s in snaps if s["label"] != "pre-restore"]
        snap_id = (stable or snaps)[0]["id"]
    else:
        snap_id = snap_ref
    root = core.snapshots_dir() / snap_id
    if not (root / "manifest.json").is_file():
        return f"找不到快照 {snap_id}"
    import json

    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    files = data.get("files") or {}
    current = {f"rules/{p.name}": p for p in core.list_rules()}
    lines = [f"**当前规则 vs 快照 {snap_id}**"]
    changed = False
    for rel, path in sorted(current.items()):
        old = files.get(rel)
        now = core.sha256_file(path)
        if old is None:
            lines.append(f"+ {rel}（快照里没有）")
            changed = True
        elif old.get("sha256") != now:
            lines.append(f"~ {rel}（已修改）")
            changed = True
    for rel in sorted(files):
        if rel.startswith("rules/") and rel not in current:
            lines.append(f"- {rel}（已删除）")
            changed = True
    if not changed:
        lines.append("无差异：规则与快照一致")
    return "\n".join(lines)


def status_payload() -> dict[str, Any]:
    """Machine-readable status for the desktop widget (``hermes purge status --json``)."""
    state = core.read_state()
    rules = core.list_rules()
    snaps = core.list_snapshots()
    conf = core.config_summary()
    latest_ok = None
    if snaps:
        ok, _bad = core.verify_snapshot(snaps[0]["id"])
        latest_ok = ok
    return {
        "enabled": bool(state.get("enabled", True)),
        "rules": len(rules),
        "chars": len(core.compose_rules()),
        "limit": core.SECTION_MAX_CHARS,
        "snapshots": len(snaps),
        "last_snapshot": snaps[0]["id"] if snaps else None,
        "last_snapshot_ok": latest_ok,
        "max_turns": conf.get("max_turns"),
        "approval_mode": conf.get("approval_mode"),
        "model": conf.get("default_model"),
        "section_registered": core.SECTION_REGISTERED,
        "data_dir": str(core.data_dir()),
        "version": core.PLUGIN_VERSION,
    }


def dispatch(raw: str) -> str:
    parts = (raw or "").strip().split()
    if not parts:
        return _status()
    cmd, rest = parts[0].lower(), parts[1:]
    arg = " ".join(rest).strip()
    if cmd in {"status", "st"}:
        return _status()
    if cmd in {"doctor", "diag", "check"}:
        return core.format_layers(core.diagnose())
    if cmd in {"on", "enable"}:
        core.set_enabled(True)
        return "purge 已开启：下一个新会话注入规则（当前会话不变）"
    if cmd in {"off", "disable"}:
        core.set_enabled(False)
        return "purge 已关闭：下一个新会话不再注入（规则文件保留）"
    if cmd in {"rules", "ls"}:
        return _rules()
    if cmd in {"show", "preview"}:
        return _show()
    if cmd in {"apply", "install"}:
        return _apply()
    if cmd in {"snapshot", "snap"}:
        return _snapshot(arg)
    if cmd in {"snapshots", "list"}:
        return _snapshots()
    if cmd in {"restore", "rollback"}:
        return _restore(arg)
    if cmd in {"diff", "compare"}:
        return _diff(arg)
    if cmd in {"help", "-h", "--help", "?"}:
        return _help()
    return f"未知子命令 {cmd}。\n\n{_help()}"


# ── slash command ────────────────────────────────────────────────────────────

def purge_command(raw_args: str) -> str:
    try:
        return dispatch(raw_args)
    except Exception as exc:  # 命令面永不把会话带崩
        return f"purge 执行出错：{type(exc).__name__}: {exc}"


# ── CLI: hermes purge ... ────────────────────────────────────────────────────

def setup_argparse(parser: Any) -> None:
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        help="status|doctor|on|off|rules|show|apply|snapshot|snapshots|restore|diff",
    )
    parser.add_argument("arg", nargs="?", default="", help="快照标签或快照 id")
    parser.add_argument("--json", dest="as_json", action="store_true", help="机器可读输出（status）")


def handle_cli(args: Any) -> Optional[int]:
    import json

    action = getattr(args, "action", "status") or "status"
    arg = getattr(args, "arg", "") or ""
    if getattr(args, "as_json", False) and action.lower() in {"status", "st", "doctor", "diag", "check"}:
        payload: dict[str, Any] = status_payload()
        if action.lower() != "status":
            payload["layers"] = core.diagnose()
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    print(dispatch(f"{action} {arg}".strip()))
    return 0
