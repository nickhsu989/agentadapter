# agentadapter

OpenCode + Claude Code on Google Colab, both wired to the **NVIDIA NIM** API — with
one-click launch, zero local setup, and session persistence to Google Drive.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/<your-username>/agentadapter/blob/main/colab.ipynb)

---

## 1-Click start (any device, no install)

1. Click the **Open In Colab** badge above (works in an incognito window too).
2. Choose a runtime — **CPU is sufficient** (no GPU needed).
3. *(Private repos only)* Add a Colab secret named **`GH_TOKEN`** with a GitHub
   Personal Access Token (🔑 sidebar in Colab → *Add secret*). The bootstrap
   cell reads it automatically; it is never hardcoded anywhere.
4. Edit **`REPO_URL`** in the bootstrap cell with your GitHub username.
5. Run the bootstrap cell. It will:
   - clone this repository onto the Colab machine
   - install Python dependencies from `requirements.txt`
   - prompt for your **`NVIDIA_API_KEY`** (hidden input; get it free at
     [build.nvidia.com](https://build.nvidia.com))
   - run `colab_setup.py`, which provisions:
     - **OpenCode** (CLI coding agent) with the NIM provider config
     - **nvd-claude-nim** proxy on `localhost:8787` (Anthropic → NIM translation)
     - **Claude Code**, pointed at the proxy
   - run smoke tests (`claude -p`, `opencode run`) to verify the full chain
6. Work inside **`/content/workspace`**.

## Keep your work

| Notebook cell | What it does |
|---|---|
| 💾 **Save** | zips `/content/workspace` + `~/.claude/projects` (Claude Code session history) → `MyDrive/agentadapter-sessions/session-<timestamp>.zip` in your Google account |
| ♻️ **Restore** | lists saved sessions from Drive and unpacks the one you pick — resume in a brand-new Colab session |
| ⬇️ **Download** | zips the workspace and downloads it to your device |

## Use from any device with git

**Install git:**

| OS | Command |
|---|---|
| Windows | `winget install --id Git.Git -e` (or [git-scm.com](https://git-scm.com/download/win)) |
| macOS | `xcode-select --install` (or `brew install git`) |
| Linux | `sudo apt install git` |

**Clone:**

```bash
git clone https://github.com/<your-username>/agentadapter.git
cd agentadapter
```

Then either open `colab.ipynb` at [colab.research.google.com](https://colab.research.google.com)
(*File → Upload notebook*) or just use the badge link above.

## Publish this repo to GitHub (first time)

```bash
cd agentadapter
git init
git add .
git commit -m "Initial commit: 1-click Colab launcher for OpenCode + Claude Code on NVIDIA NIM"
git branch -M main
git remote add origin https://github.com/<your-username>/agentadapter.git
git push -u origin main
```

After pushing, update the badge URL and `REPO_URL` in `colab.ipynb` with your username.

## Repository layout

```
agentadapter/
├── colab.ipynb               # 1-click launcher (clone → install → run)
├── colab_setup.py            # main provisioning script (idempotent)
├── colab_workspace.py        # save / restore / download session snapshots
├── requirements.txt          # Python deps (uv → nvd-claude-nim proxy)
├── config/
│   ├── opencode.json         # OpenCode provider config (deployed to ~/.config/opencode/)
│   ├── claude.settings.json  # Claude Code settings (deployed to ~/.claude/)
│   └── nim-proxy.config.yaml # NIM proxy config (deployed to ~/.config/nvd-claude-nim/)
├── opencode.jsonc            # local reference config (Windows machine)
└── settings.json             # local reference config (Windows machine)
```

## How the NVIDIA NIM wiring works

- **OpenCode** talks to NIM directly via the `nvidia` provider in
  `config/opencode.json` (OpenAI-compatible, `{env:NVIDIA_API_KEY}`).
- **Claude Code** only speaks the Anthropic Messages API, so it goes through a
  local translation proxy:
  `claude → http://localhost:8787 → nvd-claude-nim → https://integrate.api.nvidia.com/v1`
- `NVIDIA_API_KEY` is only ever held in memory / a chmod-600 env file on the VM.
  No repository file contains a real key.

## Test checklist (end-to-end)

1. Open the README badge in an **incognito** window.
2. Select a **CPU** runtime.
3. Run the bootstrap cell → watch clone, install, proxy health check, and both
   smoke tests pass.
4. Run the **Save** cell → confirm `agentadapter-sessions/session-*.zip`
   appears in your Google Drive.
5. Start a fresh session, run **Restore** → confirm your files return.

## Troubleshooting

- **OpenCode smoke test fails** — `config/opencode.json` intentionally keeps
  `baseURL: "https://nvidia.com"` verbatim from the owner's local config. If
  requests fail, switch it to the standard NIM endpoint
  `https://integrate.api.nvidia.com/v1` and re-run `python colab_setup.py`.
- **Proxy not healthy** — check `~/.config/nvd-claude-nim/proxy.log`, then
  re-run `python colab_setup.py` (it restarts the proxy idempotently).
- **Clone failed** — repo is private and no `GH_TOKEN` secret was provided, or
  `REPO_URL` still contains the `<your-username>` placeholder.
