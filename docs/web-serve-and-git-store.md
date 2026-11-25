# Self-Hosted Web/PWA Server (`mpmb-reader serve`) & Git/GitHub Storage

`mpmb-reader serve` runs the exact same QuickJS-NG + PDFium + `lopdf` MPMB engine as the desktop reader behind an HTTP/WebSocket server with an embedded iOS-first Progressive Web App (PWA) and an optional Git/GitHub storage backend.

## Features

- **Single authoritative QuickJS session**: Every original MPMB calculation, field action, timer, bookmark, and template spawn runs verbatim with zero runtime script overrides.
- **Live Acrobat dialogs, menus, and alerts over HTTP/WebSocket**: `app.execDialog`, `app.popUpMenuEx`, `app.popUpMenu`, and `app.alert` pause the sheet worker thread, push the structured dialog to the browser (`202 Accepted` + WebSocket `interaction_requested`), and resume seamlessly when the user responds.
- **iOS-first PWA UI**:
  - **Play (Table View)**: Vitals (AC, Initiative, Speed, Prof), HP bar with quick `−5/−1/+1/+5/Full` and Temp HP controls, 6 Abilities & Saves, Attacks, live toggleable Spell Slots, dynamically enumerated Limited Features, Short/Long Rest actions, Skills, and Notes.
  - **Sheet (PDF View)**: High-DPI PDFium page renders with tappable widget overlays and a `Shift` modifier toggle for MPMB spell-row options.
  - **Tools**: Original MPMB Tools menu (`ClassesButton`, etc.), Spell Sheet / Companion / Wild-Shape generators, searchable Field Inspector, Bookmarks, and Diagnostics/Console.
  - **Library & Git**: Upload/download `.pdf` files, switch characters, inspect Git status & commit history, and trigger Pull / Commit & Push.
  - **Offline resilience**: Service Worker caches the PWA shell, last character state, and rendered pages for read-only access if reception drops at the table.
- **Git/GitHub concrete store (`src/storage.rs`)**:
  - Shells out to system `git` (zero `libgit2` build overhead) using an SSH deploy key (`MPMB_GIT_SSH_KEY`) or transient `GIT_ASKPASS` HTTPS token (`MPMB_GIT_TOKEN`).
  - Atomic local saves with an external-modification SHA-256 conflict guard.
  - Writes a human-readable `<sheet>.state.json` sidecar beside `<sheet>.pdf` so `git log -p` on GitHub shows readable stat/HP/level diffs while the `.pdf` remains authoritative.
  - **Zero-data-loss divergence protection**: If `git push` is rejected (`non-fast-forward`), local commits are automatically pushed to `conflict/<host>-<timestamp>` instead of overwriting or failing silently.
  - Configurable idle auto-sync (`--git-auto-sync-secs`, default `300`, `0` disables) avoids bloating binary Git history on every HP tap.

## Local Usage

```bash
# Local directory mode
mpmb-reader serve --bind 127.0.0.1:8080 --dir ~/MPMB-Sheets

# Private GitHub repo mode (SSH deploy key)
mpmb-reader serve \
  --bind 0.0.0.0:8080 \
  --dir /data/sheets \
  --git-repo git@github.com:YOUR_USER/mpmb-characters-private.git \
  --git-branch main \
  --git-ssh-key ~/.ssh/mpmb_deploy_ed25519 \
  --git-auto-sync-secs 300
```

> **Note:** Paid MPMB Patreon PDFs and private character sheets must be stored in a **private** repository separate from this public source repository.

## Container Build & Kubernetes (k3s) Deployment

```bash
# Build the multi-stage image (never includes Testing/ or local PDFs via .containerignore)
podman build -t localhost/mpmb-reader:latest -f Containerfile .

# Import directly into a k3s node's containerd (or push to your private registry / GHCR)
podman save localhost/mpmb-reader:latest | ssh <k3s-node> 'sudo /usr/local/bin/k3s ctr images import -'

# Deploy manifests (customize packaging/k8s/git-secret.example.yaml with SOPS first)
kubectl apply -k packaging/k8s/
```

## iOS Setup

1. Connect your iPhone to your private VPN or LAN (with split DNS resolving `*.example.internal`).
2. Install and trust your internal TLS Root CA certificate (`Settings → General → VPN & Device Management`, then `Settings → General → About → Certificate Trust Settings`).
3. Open `https://mpmb.example.internal` in Safari, tap **Share → Add to Home Screen** for full-screen standalone PWA mode with safe-area support and offline caching.
