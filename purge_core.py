"""hermes-purge 内核：路径、状态、规则拼接、快照回滚、分层自检。

设计约束（与 dsh-purge 同源的四条原则）：
  本机优先 —— 全部逻辑在读本机文件，无网络、无遥测；
  可见     —— 每个动作给证据（字符数、sha256、快照 id），不靠"应该生效了"；
  可回滚   —— 任何写操作前先快照，回滚后重新校验哈希；
  不替人决定 —— 只装规则与注入层，不动审批模式、不替用户越权。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PLUGIN_ID = "hermes-purge"
SECTION_ID = "purge.core"
SECTION_MAX_CHARS = 3900
PLUGIN_VERSION = "1.2.0"

HEADER = "<!-- purge.core v1 · Hermes 执行姿态（/purge status 查看 · /purge off 关闭） -->"
FOOTER = "<!-- /purge.core -->"

# register() 成功挂上提示段后置 True。用于自检的「生效层」：CLI 进程里插件不会加载，
# 此时只能报「未知」，不能报故障。
SECTION_REGISTERED: bool = False

_DEFAULT_STATE: dict[str, Any] = {
    "enabled": True,
    "version": PLUGIN_VERSION,
    "seeded_at": None,
    "updated_at": None,
    "last_snapshot": None,
}


# ── paths ────────────────────────────────────────────────────────────────────

def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(str(get_hermes_home()))
    except Exception:
        env = os.environ.get("HERMES_HOME")
        return Path(env) if env else Path.home() / ".hermes"


def data_dir() -> Path:
    return hermes_home() / "purge"


def rules_dir() -> Path:
    return data_dir() / "rules"


def state_path() -> Path:
    return data_dir() / "state.json"


def snapshots_dir() -> Path:
    return data_dir() / "snapshots"


def packaged_rules() -> Path:
    return Path(__file__).resolve().parent / "rules"


# ── low-level io ─────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


# ── state ────────────────────────────────────────────────────────────────────

def read_state() -> dict[str, Any]:
    state = dict(_DEFAULT_STATE)
    try:
        raw = json.loads(state_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            state.update({k: raw[k] for k in raw if k in _DEFAULT_STATE or k == "version"})
            state["enabled"] = bool(raw.get("enabled", True))
    except FileNotFoundError:
        pass
    except Exception:
        # 状态文件坏了就当开启：宁可多一层规则，也不要静默失效。
        pass
    return state


def write_state(**changes: Any) -> dict[str, Any]:
    state = read_state()
    state.update(changes)
    state["version"] = PLUGIN_VERSION
    state["updated_at"] = _now()
    _atomic_write(state_path(), json.dumps(state, ensure_ascii=False, indent=2))
    return state


def set_enabled(value: bool) -> dict[str, Any]:
    return write_state(enabled=bool(value))


# ── rules ────────────────────────────────────────────────────────────────────

def list_rules() -> list[Path]:
    d = rules_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.md") if p.is_file() and not p.name.startswith("."))


def compose_rules() -> str:
    chunks: list[str] = []
    for path in list_rules():
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


def ensure_layout() -> dict[str, Any]:
    """Seed the live rules dir from the packaged defaults; never overwrite user edits."""
    d = rules_dir()
    d.mkdir(parents=True, exist_ok=True)
    snapshots_dir().mkdir(parents=True, exist_ok=True)
    seeded: list[str] = []
    src = packaged_rules()
    if src.is_dir():
        for item in sorted(src.glob("*.md")):
            dest = d / item.name
            if not dest.exists():
                shutil.copyfile(item, dest)
                seeded.append(item.name)
    state = read_state()
    if state.get("seeded_at") is None:
        state = write_state(seeded_at=_now())
    if seeded:
        state = write_state()
    return {"seeded": seeded, "rules": len(list_rules()), "state": state}


# ── prompt section ───────────────────────────────────────────────────────────

def render_section(session_info: Mapping[str, Any] | None = None) -> str:
    """Rendered once per new session. Empty string = no injection."""
    try:
        if not read_state().get("enabled", True):
            return ""
        body = compose_rules()
        if not body.strip():
            return ""
        text = f"{HEADER}\n{body}\n{FOOTER}"
        budget = SECTION_MAX_CHARS - len(HEADER) - len(FOOTER) - 2
        if len(body) > budget:
            cut = body[: max(0, budget - 60)].rstrip()
            text = f"{HEADER}\n{cut}\n\n（规则超长已截断；/purge rules 查看，上限 {SECTION_MAX_CHARS} 字符）\n{FOOTER}"
        return text
    except Exception:
        return ""


# ── snapshots ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _snap_id(label: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(c for c in label if c.isalnum() or c in "-_")[:24] or "snap"
    candidate = f"{stamp}-{safe}"
    n = 1
    while (snapshots_dir() / candidate).exists():
        n += 1
        candidate = f"{stamp}-{safe}-{n}"
    return candidate


def snapshot(label: str = "manual") -> dict[str, Any]:
    """Copy rules + state into snapshots/<id>/files and write a sha256 manifest."""
    sid = _snap_id(label)
    root = snapshots_dir() / sid
    files_root = root / "files"
    files_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "id": sid,
        "label": label,
        "created_at": _now(),
        "plugin_version": PLUGIN_VERSION,
        "files": {},
    }
    if rules_dir().is_dir():
        for src in sorted(rules_dir().glob("*.md")):
            if src.is_file():
                dest = files_root / "rules" / src.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                manifest["files"][f"rules/{src.name}"] = {
                    "sha256": sha256_file(dest),
                    "size": dest.stat().st_size,
                }
    if state_path().is_file():
        dest = files_root / "state.json"
        shutil.copyfile(state_path(), dest)
        manifest["files"]["state.json"] = {
            "sha256": sha256_file(dest),
            "size": dest.stat().st_size,
        }
    _atomic_write(root / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    ok, bad = verify_snapshot(sid)
    if not ok:
        raise RuntimeError(f"快照写入后校验失败：{', '.join(bad)}")
    write_state(last_snapshot=sid)
    return manifest


def list_snapshots() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    d = snapshots_dir()
    if not d.is_dir():
        return out
    for item in sorted(d.iterdir(), reverse=True):
        manifest = item / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append(
            {
                "id": data.get("id") or item.name,
                "label": data.get("label") or "",
                "created_at": data.get("created_at") or "",
                "files": len(data.get("files") or {}),
            }
        )
    return out


def verify_snapshot(snap_id: str) -> tuple[bool, list[str]]:
    root = snapshots_dir() / snap_id
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return False, [f"找不到快照 {snap_id}"]
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"manifest 读取失败: {exc}"]
    bad: list[str] = []
    for rel, meta in (data.get("files") or {}).items():
        target = root / "files" / rel
        if not target.is_file():
            bad.append(f"{rel}: 缺失")
            continue
        actual = sha256_file(target)
        if actual != (meta or {}).get("sha256"):
            bad.append(f"{rel}: 哈希不符")
    return (not bad), bad


def restore(snap_id: str) -> dict[str, Any]:
    root = snapshots_dir() / snap_id
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"找不到快照 {snap_id}")
    ok, bad = verify_snapshot(snap_id)
    if not ok:
        raise RuntimeError("快照自身校验失败，拒绝回滚：" + ", ".join(bad))

    pre = snapshot("pre-restore")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    for stale in rules_dir().glob("*.md"):
        try:
            stale.unlink()
        except Exception:
            pass
    restored: list[str] = []
    for rel in (data.get("files") or {}):
        src = root / "files" / rel
        if rel == "state.json":
            dest = state_path()
        elif rel.startswith("rules/"):
            dest = rules_dir() / Path(rel).name
        else:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        restored.append(rel)

    # 回滚后重新核对目标文件哈希
    mismatched = [
        rel for rel, meta in (data.get("files") or {}).items()
        if (root / "files" / rel).is_file()
        and ((rules_dir() / Path(rel).name) if rel.startswith("rules/") else state_path()).is_file()
        and sha256_file((rules_dir() / Path(rel).name) if rel.startswith("rules/") else state_path())
        != (meta or {}).get("sha256")
    ]
    write_state(last_snapshot=snap_id)
    return {
        "id": snap_id,
        "restored": restored,
        "mismatched": mismatched,
        "pre_restore_snapshot": pre.get("id"),
    }


# ── config peek + diagnostics ────────────────────────────────────────────────

def _scalar(section: str, key: str, default: Any = None) -> Any:
    """Minimal reader for ``section:\\n  key: value`` in config.yaml — no yaml import, no private core seam.

    config.yaml is generated by Hermes with two-space indentation under a top-level section, so a
    line scan is sufficient for the three scalars this plugin reports. Anything odd returns *default*:
    the diagnostic says "unknown", never a guess.
    """
    path = hermes_home() / "config.yaml"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return default
    inside = False
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            inside = line.split(":", 1)[0].strip() == section
            continue
        if not inside:
            continue
        stripped = line.strip()
        if not stripped.startswith(f"{key}:"):
            continue
        value = stripped.split(":", 1)[1].split("#", 1)[0].strip().strip("'\"")
        if value in {"", "~", "null", "None"}:
            return default
        if value.isdigit():
            return int(value)
        return value
    return default


def config_summary() -> dict[str, Any]:
    return {
        "max_turns": _scalar("agent", "max_turns"),
        "approval_mode": _scalar("approvals", "mode"),
        "default_model": _scalar("model", "default"),
    }


def diagnose() -> list[dict[str, Any]]:
    """Five layers, each with a verdict: ok / warn / bad."""
    layers: list[dict[str, Any]] = []
    state = read_state()

    # 1. 插件层
    files = [Path(__file__).resolve().parent / n for n in ("plugin.yaml", "__init__.py", "purge_core.py")]
    missing = [f.name for f in files if not f.is_file()]
    layers.append({
        "layer": "插件层",
        "level": "bad" if missing else "ok",
        "detail": f"v{PLUGIN_VERSION} · 缺失 {', '.join(missing)}" if missing else f"v{PLUGIN_VERSION} · 文件齐全",
    })

    # 2. 注入层
    rules = list_rules()
    body = compose_rules()
    if not state.get("enabled", True):
        layers.append({"layer": "注入层", "level": "warn", "detail": "已关闭（/purge on 重新开启）"})
    elif not rules:
        layers.append({"layer": "注入层", "level": "bad", "detail": "规则目录为空（/purge apply 重新播种）"})
    else:
        level = "warn" if len(body) > SECTION_MAX_CHARS else "ok"
        layers.append({
            "layer": "注入层",
            "level": level,
            "detail": f"{len(rules)} 条规则 · {len(body)}/{SECTION_MAX_CHARS} 字符"
                      + ("（超限会被截断）" if level == "warn" else ""),
        })

    # 3. 注册/生效层
    if SECTION_REGISTERED:
        layers.append({"layer": "生效层", "level": "ok", "detail": "已注册；新会话渲染，当前会话保持冻结"})
    else:
        layers.append({
            "layer": "生效层",
            "level": "warn",
            "detail": "本进程未加载插件（CLI 进程下属正常）；以会话内 /purge doctor 为准",
        })

    # 4. 配置层（只报告，不修改）
    conf = config_summary()
    notes: list[str] = []
    if isinstance(conf["max_turns"], int) and conf["max_turns"] < 60:
        notes.append(f"max_turns={conf['max_turns']} 偏低")
    if conf["approval_mode"] == "manual":
        notes.append("approvals.mode=manual（每个危险命令都问）")
    layers.append({
        "layer": "配置层",
        "level": "warn" if notes else "ok",
        "detail": "；".join(notes) if notes
                  else f"max_turns={conf['max_turns']} · approvals={conf['approval_mode']} · model={conf['default_model']}",
    })

    # 5. 备份层
    snaps = list_snapshots()
    if not snaps:
        layers.append({"layer": "备份层", "level": "warn", "detail": "还没有快照（/purge snapshot 建一个基线）"})
    else:
        ok, bad = verify_snapshot(snaps[0]["id"])
        layers.append({
            "layer": "备份层",
            "level": "ok" if ok else "bad",
            "detail": f"{len(snaps)} 个快照 · 最新 {snaps[0]['id']}" + ("" if ok else f" · 校验失败 {bad}"),
        })
    return layers


def format_layers(layers: list[dict[str, Any]]) -> str:
    icon = {"ok": "✓", "warn": "!", "bad": "✗"}
    lines = ["**purge 分层自检**"]
    for item in layers:
        lines.append(f"{icon.get(item['level'], '?')} {item['layer']}：{item['detail']}")
    bads = sum(1 for i in layers if i["level"] == "bad")
    warns = sum(1 for i in layers if i["level"] == "warn")
    verdict = "就绪" if bads == 0 and warns == 0 else ("可用，有告警" if bads == 0 else "有故障层，按上面 ✗ 修")
    lines.append(f"\n结论：{verdict}")
    return "\n".join(lines)
