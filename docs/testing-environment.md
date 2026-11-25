# Windows Adobe Acrobat Reference Environment

Development validates native MPMB behavior against real Adobe Acrobat Reader running in a local Windows 11 KVM VM. The harness executes original MPMB JavaScript over localhost SSH with no external API keys required.

## Configuration (`.env`)

Machine-specific VM settings are configured via environment variables or a local gitignored `.env` file at the repository root (copied from `.env.example`):

```bash
cp .env.example .env
```

Supported variables (shell environment variables always take precedence over `.env`; git worktrees automatically fall back to the main checkout's `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `MPMB_WIN_USER` | `mpmb-test` | Windows VM account username |
| `MPMB_WIN_HOST` | `127.0.0.1` | SSH/SCP host |
| `MPMB_WIN_PORT` | `2222` | SSH/SCP port |
| `MPMB_WIN_SCP_TARGET` | `<MPMB_WIN_USER>@<MPMB_WIN_HOST>` | Explicit SSH/SCP target |
| `MPMB_WIN_ROOT` | `C:\Users\<MPMB_WIN_USER>\MPMB-Testing` | Windows harness root directory |
| `MPMB_WIN_SSH_KEY` | `~/.ssh/mpmb_win_vm` | Private SSH key path |
| `MPMB_VM_NAME` | `mpmb-windows11` | Local libvirt domain name |
| `MPMB_MUX_DIR` | `~/.cache/mpmb-testing` | SSH control-socket & desktop-lock directory |
| `MPMB_PYTHON` | `python3` / `.venv/bin/python3` | Python interpreter with `tools/acrobat/requirements.txt` |
| `MPMB_ENV_FILE` | `<repo>/.env` | Override `.env` file path (set empty to disable) |

## Quick Start

```bash
tools/acrobat/run up
tools/acrobat/run preflight
tools/acrobat/run smoke
tools/acrobat/run readiness
tools/acrobat/run imports
tools/acrobat/run stability output/testing/readiness-<timestamp>.json
tools/acrobat/run render output/testing/readiness-<timestamp>.json
```

Keep the Windows desktop unlocked and its keyboard/mouse idle during a suite. The interactive helper starts at Windows logon. Install Python dependencies from `tools/acrobat/requirements.txt` (e.g., in `.venv`) and point `MPMB_PYTHON` to that interpreter if system `python3` lacks `pypdf`.

If the VM is libvirt managed-saved, `tools/acrobat/run up` resumes the saved state cleanly; reconnect and rerun `preflight`/`readiness` before using it as an oracle.

## Fixtures & Independent Verification

- `docs/fixtures.json` records expected local filenames and SHA-256 hashes only (paid MPMB PDFs are never committed).
- Windows fixture copies live read-only under `<MPMB_WIN_ROOT>\fixtures`; every suite works on unique disposable copies under `runs`.
- Local outputs and screenshots stay under gitignored `output/testing`.
- The synthetic manual add-on fixture is `Testing/addons/readiness-sentinel.js`.
- Saved PDFs are independently verified on Linux with `pypdf` (canonical `/T` values, page widgets, decoded appearance streams, original embedded document-script hashes) and rendered with Poppler.
- Do not edit fingerprinted `tools/acrobat` files, `docs/fixtures.json`, `docs/environment-lock.json`, or `Testing/addons/readiness-sentinel.js` while a qualification run is active; the harness verifies their SHA-256 fingerprint.

## Serialized Control CLI

```bash
tools/acrobat/run control health
tools/acrobat/run control inspect
tools/acrobat/run control ready runs/example.pdf
tools/acrobat/run control js read --params '{"path":"runs/example.pdf","fields":["PC Name","Str","Str Mod"]}'
tools/acrobat/run control js focus --params '{"path":"runs/example.pdf","field":"PC Name"}'
tools/acrobat/run control paste 'Exact text'
tools/acrobat/run control js save --params '{"path":"runs/example.pdf","output":"runs/example-saved.pdf"}'
tools/acrobat/run control screenshot
tools/acrobat/run inventory
```

Additional guarded controls for native Windows dialogs and owner-drawn Reader menus:

- `control dialog-control OWNER HANDLE` / `focus-control OWNER HANDLE` / `click-dialog-control OWNER HANDLE NAME`: inspect, focus, or physically click an observed, ownership-verified native control.
- `control inspect-focused` / `inspect-menu OWNER` / `activate-menu OWNER POSITION NAME`: inspect and activate observed Reader popup menu items via isolated UI Automation (`CreateNoWindow=true`).
- File imports use the real Windows file picker (`control js call ... --async`, `control select-file REQUEST_ID runs/addon.js`, `control result REQUEST_ID`).

## Protocol 3 Application-Menu Bridge

Protocol 3 invokes the trusted application-folder adapter (`tools/acrobat/windows/mpmb-testing.js`, which auto-detects `/C/Users/<active-user>/MPMB-Testing/` via `app.getPath("user", "documents")`) from the target document's File menu. Original MPMB functions and their follow-up timers execute in that document's menu context:

- `ready` waits for `InitializeEverything`/`CalcMod`, enabled calculation flags, cleared display delay, and the document-context startup barrier timer.
- Result alerts escape literal ampersands before alert delivery (Reader alert Static text doubles unescaped `&`) and defer receipt display on a retained 0 ms timer after synchronous execution returns.
- Document closing verifies exactly one open document, exits Reader cleanly, and confirms all Reader processes terminate before cold reopen.
- Host commands serialize through `desktop_lock()` in `MPMB_MUX_DIR`; never run competing suites against the same Windows desktop.

## Deployment & VM Checkpoints

`tools/acrobat/run bootstrap` deploys the Windows scripts, verifies/uploads fixtures, and registers the interactive logon task. `preflight` checks protocol version, pinned Reader build (`docs/environment-lock.json`), and deployed script SHA-256 hashes.

Checkpoints include system disk, NVRAM, TPM state, and domain XML, stored locally under `~/VirtualMachines/<MPMB_VM_NAME>/checkpoints` (excluded from Git). Shut Windows down cleanly before checkpoint operations:

```bash
tools/acrobat/run vm create baseline-name
tools/acrobat/run vm list
tools/acrobat/run vm restore baseline-name
tools/acrobat/run up
```

Restore automatically creates a recoverable pre-restore checkpoint first. After restoring a checkpoint, rerun `up`, `preflight`, and `readiness`.
