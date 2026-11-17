"""
colab_workspace.py — save / restore / download Colab work so sessions resume.

Save     : zips /content/workspace (+ ~/.claude/projects history) into Google
           Drive at MyDrive/agentadapter-sessions/session-<timestamp>.zip
Restore  : picks one of those zips and unpacks it back into place, so a brand
           new Colab session can resume where the last one stopped.
Download : zips the workspace and hands it to the browser.

Keep everything you produce during a session inside /content/workspace.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

WORKSPACE = Path("/content/workspace")
DRIVE = Path("/content/drive")
SESSIONS_DIR = DRIVE / "MyDrive" / "agentadapter-sessions"
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


def _mount_drive() -> None:
    """Mount Google Drive (idempotent) and make sure the sessions dir exists."""
    if not (DRIVE / "MyDrive").exists():
        from google.colab import drive  # only available on Colab
        drive.mount(str(DRIVE))
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _add_tree(zf: zipfile.ZipFile, src: Path, arc_root: str) -> int:
    """Recursively add src into the archive under arc_root/. Returns file count."""
    count = 0
    for root, _dirs, files in os.walk(src):
        for name in files:
            path = Path(root) / name
            try:
                zf.write(path, arcname=f"{arc_root}/{path.relative_to(src)}")
                count += 1
            except OSError:
                print(f"  ⚠ skipped unreadable file: {path}")
    return count


def save_snapshot(label: str | None = None) -> Path:
    """Zip the workspace (+ Claude history) into Google Drive. Returns the path."""
    _mount_drive()
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"session-{stamp}" + (f"-{label}" if label else "") + ".zip"
    target = SESSIONS_DIR / name

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        n_workspace = _add_tree(zf, WORKSPACE, "workspace")
        n_claude = (
            _add_tree(zf, CLAUDE_PROJECTS, "claude-projects")
            if CLAUDE_PROJECTS.exists()
            else 0
        )

    size_mb = target.stat().st_size / 1e6
    print(
        f"✅ Saved {n_workspace} workspace file(s) + {n_claude} Claude history "
        f"file(s)\n   → {target}  ({size_mb:.1f} MB)"
    )
    return target


def restore_snapshot() -> Path | None:
    """List Drive sessions, restore the chosen one. Returns the archive used."""
    _mount_drive()
    sessions = sorted(SESSIONS_DIR.glob("session-*.zip"))
    if not sessions:
        print("ℹ No saved sessions found in Drive (MyDrive/agentadapter-sessions).")
        return None

    print("Saved sessions:")
    for i, s in enumerate(sessions, 1):
        print(f"  [{i}] {s.name}")

    raw = input(f"Restore which? [1-{len(sessions)}, default {len(sessions)}]: ").strip()
    idx = int(raw) if raw.isdigit() and 1 <= int(raw) <= len(sessions) else len(sessions)
    archive = sessions[idx - 1]

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    CLAUDE_PROJECTS.mkdir(parents=True, exist_ok=True)

    restored = 0
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            prefix, _, rel = member.partition("/")
            if prefix == "workspace":
                base = WORKSPACE
            elif prefix == "claude-projects":
                base = CLAUDE_PROJECTS
            else:
                continue
            if not rel:
                continue
            dest = (base / rel).resolve()
            if not str(dest).startswith(str(base.resolve())):
                print(f"  ⚠ zip-slip blocked: {member}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as fsrc, open(dest, "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
            restored += 1

    print(f"✅ Restored {restored} file(s) from {archive.name}")
    print("ℹ Workspace → /content/workspace · Claude history → ~/.claude/projects")
    return archive


def download_snapshot() -> None:
    """Zip the current workspace and trigger a browser download."""
    from google.colab import files  # only available on Colab

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = Path(f"/content/workspace-{stamp}.zip")

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        n = _add_tree(zf, WORKSPACE, "workspace")

    print(f"• Zipped {n} file(s) → {target.name}; starting browser download…")
    files.download(str(target))
