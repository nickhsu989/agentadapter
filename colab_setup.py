#!/usr/bin/env python3
"""
colab_setup.py — provision a fresh Google Colab VM (or any Linux box) with:

  1. OpenCode        CLI coding agent, configured for NVIDIA NIM
  2. nvd-claude-nim  Anthropic -> NIM translation proxy on localhost:8787
  3. Claude Code     Anthropic CLI, pointed at the proxy

All deploy configs live in ./config (relative to this script); this mirrors
the setup proven on the owner's local WSL instance. The script is idempotent
and safe to re-run — existing installs are refreshed, not duplicated.

Required environment:
  NVIDIA_API_KEY   NVIDIA NIM API key (https://build.nvidia.com)
                   The launcher notebook prompts for it before calling this.

Usage (from the repository root):
  python colab_setup.py             # full setup + smoke tests
  python colab_setup.py --no-smoke  # skip the end-to-end model smoke tests
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = REPO_ROOT / "config"

HOME = Path.home()
OPENCODE_BIN = HOME / ".opencode" / "bin" / "opencode"
OPENCODE_CONFIG = HOME / ".config" / "opencode" / "opencode.json"
NIM_CFG_DIR = HOME / ".config" / "nvd-claude-nim"
NIM_BIN = HOME / ".local" / "bin" / "nim"
NIM_CONFIG = NIM_CFG_DIR / "config.yaml"
NIM_ENV = NIM_CFG_DIR / "env"
NIM_LOG = NIM_CFG_DIR / "proxy.log"
CLAUDE_DIR = HOME / ".claude"
CLAUDE_SETTINGS = CLAUDE_DIR / "settings.json"

PROXY_PORT = 8787
DEFAULT_NIM_MODEL = "z-ai/glm-5.3-flash"

_step = 0


def header(title: str) -> None:
    global _step
    _step += 1
    bar = "=" * max(0, 58 - len(title))
    print(f"\n=== Step {_step}: {title} {bar}")


def run(cmd: str | list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, showing it and streaming output. Never raises."""
    shown = cmd if isinstance(cmd, str) else " ".join(map(str, cmd))
    print(f"$ {shown}")
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=False, **kwargs)


def require_posix() -> None:
    if os.name != "posix":
        sys.exit(
            "✖ This script targets Linux (Google Colab / WSL). "
            "Run it inside the Colab notebook, not on Windows."
        )


def require_api_key() -> str:
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        sys.exit(
            "✖ NVIDIA_API_KEY is not set. The launcher notebook prompts for it "
            "before running this script — re-run the bootstrap cell."
        )
    if not key.startswith("nvapi-"):
        print("⚠ Key does not start with 'nvapi-' — continuing anyway.")
    return key


def wait_for_port(port: int, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(1.0)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(1.0)
    return False


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #

def install_opencode() -> None:
    header("Install OpenCode")
    if OPENCODE_BIN.exists():
        print(f"• Found existing install at {OPENCODE_BIN} — skipping download.")
    else:
        run("curl -fsSL https://opencode.ai/v2/install | bash")
    os.environ["PATH"] = f"{OPENCODE_BIN.parent}:{os.environ.get('PATH', '')}"
    result = run([str(OPENCODE_BIN), "--version"], capture_output=True, text=True)
    version = (result.stdout or result.stderr).strip().splitlines()
    print(f"• OpenCode: {version[0] if version else 'installed (version unknown)'}")


def deploy_opencode_config() -> None:
    header("Deploy OpenCode config")
    src = CONFIG_DIR / "opencode.json"
    OPENCODE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, OPENCODE_CONFIG)
    print(f"• {src} → {OPENCODE_CONFIG}")
    print("ℹ apiKey uses {env:NVIDIA_API_KEY} — resolved from the environment at runtime.")


def install_nim_proxy() -> None:
    header("Install uv + nvd-claude-nim (Anthropic→NIM proxy)")
    if shutil.which("uv") is None:
        run(f"{sys.executable} -m pip install -q uv")
    else:
        print("• uv already installed.")
    if NIM_BIN.exists():
        print(f"• Found existing tool at {NIM_BIN} — skipping install (delete it to force a reinstall).")
    else:
        run(["uv", "tool", "install", "nvd-claude-nim"])
    os.environ["PATH"] = f"{NIM_BIN.parent}:{os.environ.get('PATH', '')}"


def deploy_proxy_config(api_key: str) -> None:
    header("Deploy proxy config + secret env")
    NIM_CFG_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(CONFIG_DIR / "nim-proxy.config.yaml", NIM_CONFIG)
    print(f"• config → {NIM_CONFIG}")

    env_file = (
        f"NVIDIA_API_KEY={api_key}\n"
        f"PROXY_CONFIG={NIM_CONFIG}\n"
        f"PROXY_HOST=0.0.0.0\n"
        f"PROXY_PORT={PROXY_PORT}\n"
        f"DEFAULT_NVIDIA_MODEL={DEFAULT_NIM_MODEL}\n"
    )
    NIM_ENV.write_text(env_file)
    os.chmod(NIM_ENV, 0o600)
    print(f"• secret env → {NIM_ENV} (chmod 600)")

    # Mirror the env vars into this process, like the local systemd unit did.
    os.environ.update(
        NVIDIA_API_KEY=api_key,
        PROXY_CONFIG=str(NIM_CONFIG),
        PROXY_HOST="0.0.0.0",
        PROXY_PORT=str(PROXY_PORT),
        DEFAULT_NVIDIA_MODEL=DEFAULT_NIM_MODEL,
    )


def start_proxy() -> None:
    header("Launch nim proxy on localhost:8787")
    run("pkill -f 'nim proxy' || true")  # idempotency: replace any old instance
    time.sleep(1)
    with open(NIM_LOG, "ab") as log:
        proc = subprocess.Popen(
            [str(NIM_BIN), "proxy"],
            stdout=log,
            stderr=log,
            start_new_session=True,  # survive this script's exit
        )
    print(f"• nim proxy launched (pid {proc.pid}); log: {NIM_LOG}")
    if wait_for_port(PROXY_PORT):
        print(f"✅ Proxy is listening on 127.0.0.1:{PROXY_PORT}")
        run([str(NIM_BIN), "status"])
    else:
        print(f"✖ Proxy did not open port {PROXY_PORT} in time — check {NIM_LOG}")


def install_claude_code() -> None:
    header("Install Node.js (if missing) + Claude Code")
    if shutil.which("node") is None:
        print("• Node.js not found — installing Node 20 (NodeSource)…")
        run("curl -fsSL https://deb.nodesource.com/setup_20.x | bash -")
        run("apt-get install -y -qq nodejs")
    else:
        run(["node", "--version"])
    run("npm install -g @anthropic-ai/claude-code")


def deploy_claude_settings() -> None:
    header("Deploy Claude Code settings")
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(CONFIG_DIR / "claude.settings.json", CLAUDE_SETTINGS)
    print(f"• {CONFIG_DIR / 'claude.settings.json'} → {CLAUDE_SETTINGS}")
    print("ℹ ANTHROPIC_BASE_URL=http://localhost:8787 — Claude Code will talk to the NIM proxy.")


def smoke_tests(skip: bool) -> None:
    header("Smoke tests")
    if skip:
        print("• Skipped (--no-smoke).")
        return

    print("\n[1/3] OpenCode CLI")
    run([str(OPENCODE_BIN), "--version"])

    print("\n[2/3] Claude Code → proxy → NIM")
    claude = shutil.which("claude")
    if claude is None:
        print("⚠ 'claude' binary not found on PATH — skipping this test.")
    else:
        try:
            result = subprocess.run(
                [claude, "-p", "Reply with exactly: OK"],
                capture_output=True, text=True, timeout=240,
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"✅ Claude Code responded: {result.stdout.strip()[:200]}")
            else:
                print(f"⚠ claude -p failed (rc={result.returncode})")
                print((result.stderr or result.stdout).strip()[:500])
        except subprocess.TimeoutExpired:
            print("⚠ claude -p timed out after 240s.")

    print("\n[3/3] OpenCode → NIM")
    try:
        result = subprocess.run(
            [str(OPENCODE_BIN), "run", "Reply with exactly: OK"],
            capture_output=True, text=True, timeout=240,
        )
        if result.returncode == 0 and result.stdout.strip():
            print(f"✅ OpenCode responded: {result.stdout.strip()[:200]}")
        else:
            print(f"⚠ opencode run failed (rc={result.returncode})")
            print((result.stderr or result.stdout).strip()[:500])
            print(
                "ℹ HINT: config/opencode.json intentionally keeps baseURL "
                "'https://nvidia.com' verbatim. If requests fail, the standard "
                "NIM endpoint is https://integrate.api.nvidia.com/v1 — edit "
                "config/opencode.json and re-run this script."
            )
    except subprocess.TimeoutExpired:
        print("⚠ opencode run timed out after 240s.")


def summary() -> None:
    print("\n" + "=" * 66)
    print("✅ Setup complete")
    print("=" * 66)
    print(f"""
Next steps in this Colab session:

  opencode                      # OpenCode TUI (use a terminal cell or tmux)
  opencode run "your prompt"    # one-shot OpenCode from a cell
  claude                        # Claude Code TUI
  claude -p "your prompt"       # one-shot Claude Code from a cell

Everything you create should live in /content/workspace —
use the notebook's Save / Restore / Download cells to persist it.
""")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-smoke", action="store_true", help="skip model smoke tests")
    args = parser.parse_args()

    require_posix()
    api_key = require_api_key()

    install_opencode()
    deploy_opencode_config()
    install_nim_proxy()
    deploy_proxy_config(api_key)
    start_proxy()
    install_claude_code()
    deploy_claude_settings()
    smoke_tests(args.no_smoke)
    summary()


if __name__ == "__main__":
    main()
