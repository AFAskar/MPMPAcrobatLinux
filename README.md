# MPMB Reader

A native Rust PDF reader for running [MorePurpleMoreBetter (MPMB)](https://www.flapkan.com/) interactive D&D 5e (2014 & 2024) PDF character sheets on Linux and Windows without Adobe Acrobat Reader.

## Overview

MPMB Reader executes the original embedded PDF JavaScript verbatim inside a single authoritative QuickJS-NG form state, renders pages via PDFium, persists interactive PDFs with `lopdf`, and provides a Dark/Light themed desktop UI (`eframe`/`egui`).

- **Zero runtime script overrides:** Original embedded MPMB scripts run unmodified to match Adobe Acrobat Reader behavior faithfully.
- **Interactive desktop UI:** Obsidian Slate & Gold (Dark) and Ivory & Ink (Light) themes, live Character Quick-Card, searchable Field Inspector, Bookmarks panel, native modal dialogs (`app.execDialog`, `app.popUpMenuEx`, `app.alert`), and atomic non-destructive saves.
- **Cross-platform packaging:** Prebuilt releases for Linux (Flatpak, AppImage, RPM) and Windows (Portable ZIP, Installer EXE) with `SHA256SUMS.txt`.

> **Compatibility scope:** Full MPMB compatibility across every subclass choice, third-party add-on, and Acrobat-Pro-only authoring API remains in progress. This reader is intended for trusted local MPMB sheets and user-approved add-ons, not untrusted arbitrary PDFs.

## Installation

Download a prebuilt package from [GitHub Releases](https://github.com/AFAskar/MPMPAcrobatLinux/releases):

- **Linux Flatpak:** `mpmb-reader-<ver>-x86_64.flatpak` ([`packaging/flatpak/`](packaging/flatpak/))
- **Linux AppImage:** `MPMB-Reader-<ver>-x86_64.AppImage` ([`packaging/appimage/`](packaging/appimage/))
- **Linux RPM:** `mpmb-reader-<ver>-1.x86_64.rpm` ([`packaging/rpm/`](packaging/rpm/))
- **Windows Portable ZIP:** `MPMB-Reader-<ver>-windows-x64-portable.zip` ([`packaging/windows/`](packaging/windows/))
- **Windows Installer EXE:** `MPMB-Reader-<ver>-windows-x64-setup.exe` ([`packaging/windows/mpmb-reader.iss`](packaging/windows/mpmb-reader.iss))

## Building from Source

Prerequisites on Linux: Rust/Cargo, a C toolchain, OpenGL/Mesa, X11 or Wayland development libraries, `zenity` (file dialogs), Poppler, and DejaVu Sans fonts.

```bash
# Download pinned PDFium binary (SHA-256 verified)
tools/native/setup-pdfium

# Build and run on your authorized MPMB sheet
cargo build --locked
tools/native/run "/path/to/your-mpmb-sheet.pdf"

# Run Rust & Python unit tests
cargo test --locked
python3 -m unittest discover -s tools/native -p 'test_*.py'
```

See [docs/native-reader.md](docs/native-reader.md) for architecture details, CLI diagnostic options, and compatibility boundaries.

## Local-Only Content (MPMB PDFs)

Paid MPMB Patreon PDFs and personal character sheets are **not** included in this repository and must never be committed or redistributed. Obtain your own authorized copies directly from MPMB.

- `docs/fixtures.json` records expected local filenames and SHA-256 integrity hashes only (no PDF bytes or extracted scripts).
- `*.pdf`, `output/`, VM disks/checkpoints, credentials, and `.env` files are excluded via [`.gitignore`](.gitignore).
- `Testing/addons/readiness-sentinel.js` is a small synthetic test fixture, not an MPMB sheet.

## Pinned Upstream Source Reference

The public upstream 2024 MPMB script repository is linked as a pinned Git submodule at `2024_MPMBs-Character-Record-Sheet/` (`5d6e57c861643ca77764131bd5dc865389879667`) for reference only:

```bash
git clone --recurse-submodules https://github.com/AFAskar/MPMPAcrobatLinux.git
# or for an existing clone:
git submodule update --init --recursive
```

## Windows Acrobat Reference Harness (Development)

Contributors validating parity against real Adobe Acrobat Reader in a local Windows VM can configure local connection settings via a gitignored `.env` file:

```bash
cp .env.example .env
# Edit .env with your local VM user, SSH key, and host/port if non-default
tools/acrobat/run up
tools/acrobat/run smoke
```

See [docs/testing-environment.md](docs/testing-environment.md) for setup, protocol details, and VM checkpoint usage, and [AGENTS.md](AGENTS.md) for contributor/agent engineering rules.

## License

Licensed under the [MIT License](LICENSE). Third-party bundled runtime licenses (PDFium and DejaVu Fonts) are included in packaged releases.
