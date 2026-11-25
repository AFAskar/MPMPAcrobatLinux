# Linux-native MPMB reader

The goal is a native Rust PDF reader that executes the original MPMB scripts with Acrobat-compatible behavior. The repository now includes an experimental native Rust reader, an Acrobat API bridge for original embedded scripts, and the qualified Windows reference harness. The defined first vertical slice works; full MPMB compatibility remains in progress.

The compatibility target is all MPMB behavior in the three authorized PDFs under `Testing/`, including every predefined class choice and real table usage. That target is **not yet met**. Passing the first milestone or selected generated workflows does not establish full MPMB compatibility; general Acrobat JavaScript coverage is not the acceptance target.

Start with [AGENTS.md](AGENTS.md), the [development handoff](docs/development-handoff.md), and the [Acrobat environment guide](docs/testing-environment.md).

## Local reference environment

Development runs on Fedora. Real Adobe Acrobat Reader runs in a local Windows VM with 4 vCPUs and 4 GiB RAM. The direct test harness uses localhost SSH and requires no API key or additional Windows model turn.

```bash
tools/acrobat/run up
tools/acrobat/run smoke
```

The recorded qualification passed 27 preflight checks, 24 readiness cases, two file-import cases and six stability cases. See the [readiness audit](docs/testing-readiness-audit.md) for scope, evidence and limitations. Recheck the live environment before development tests.

## Pinned source reference

The upstream 2024 MPMB source is a submodule at `2024_MPMBs-Character-Record-Sheet/`, pinned to `5d6e57c861643ca77764131bd5dc865389879667`. It is reference material for the agent; do not edit it or advance it implicitly. The parent repository records its URL and commit pointer while upstream retains its own history.

For a fresh clone:

```bash
git clone --recurse-submodules git@github.com:AFAskar/MPMPAcrobatLinux.git
cd MPMPAcrobatLinux
```

For an existing clone:

```bash
git submodule update --init --recursive
git submodule status
```

These commands retrieve the public source reference, not the paid PDFs or private test evidence. See the upstream checkout’s README and LICENSE for its terms. Use the pinned revision rather than `git pull` or `git submodule update --remote` during compatibility work.

## Local-only content

The MPMB reference PDFs were acquired as paid Patreon content. They are not included or licensed for redistribution by this repository. Keep them, saved characters, generated PDFs and extracted document scripts local. Obtain your own authorized copies; `docs/fixtures.json` records expected filenames and integrity hashes only.

Generated evidence under `output/`, VM state, credentials and build outputs are also ignored. The small synthetic sentinel under `Testing/addons/` is test instrumentation, not an MPMB sheet.

## Native application

```bash
tools/native/setup-pdfium
cargo build --locked
tools/native/run "Testing/<authorized sheet filename>.pdf"
cargo test --locked
tools/native/acceptance
tools/native/extended
tools/native/generated
```

See [native build/run and architecture](docs/native-reader.md), the [compatibility matrix](docs/native-compatibility.json), [readiness matrix](docs/2024-readiness.md), and the [current handoff](docs/development-handoff.md). The application uses PDFium for rendering, QuickJS-NG for the original scripts, lopdf for interactive PDF persistence, and one live JavaScript form state inside a Dark/Light themed desktop UI. Original embedded PDF scripts execute verbatim with **zero runtime overrides** (`repairs: []`; upstream PDF script defects such as the 2024 `v24.2.0+261023` `ApplyWildshape` `ReferenceError` are reproduced faithfully rather than monkey-patched). Wider compatibility (per-subclass non-default feature choices / per-subclass Reader parity and Acrobat-Pro-only APIs) remains explicitly scoped. Evidence and screenshots stay local under ignored `output/testing`.

## CI/CD & Release Packaging

GitHub Actions builds and verifies Linux (`ubuntu-latest`: `rustfmt`, strict Clippy, Rust tests, and normal/`-O` Python tests) and Windows (`windows-latest`: strict Clippy, Rust tests, release build) in [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Tagging `v*` (or manually running [`.github/workflows/release.yml`](.github/workflows/release.yml)) publishes all five packaged formats with `SHA256SUMS.txt`:

- **Linux Flatpak** (`mpmb-reader-<ver>-x86_64.flatpak`) — [`packaging/flatpak/`](packaging/flatpak/)
- **Linux AppImage** (`MPMB-Reader-<ver>-x86_64.AppImage`) — [`packaging/appimage/`](packaging/appimage/)
- **Linux RPM** (`mpmb-reader-<ver>-1.x86_64.rpm`) — [`packaging/rpm/`](packaging/rpm/)
- **Windows Portable ZIP** (`MPMB-Reader-<ver>-windows-x64-portable.zip`) — [`packaging/windows/`](packaging/windows/)
- **Windows Installer EXE** (`MPMB-Reader-<ver>-windows-x64-setup.exe`) — [`packaging/windows/mpmb-reader.iss`](packaging/windows/mpmb-reader.iss)

## Implementation starting point

The original documentation baseline preceded the native implementation. Run `git log -5 --oneline` to see the focused baseline commits and `git status --short` to verify a clean working tree. The handoff identifies the harness commit and the next development milestone.
