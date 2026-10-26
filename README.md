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

See [native build/run and architecture](docs/native-reader.md), the [compatibility matrix](docs/native-compatibility.json), and the [current handoff](docs/development-handoff.md). The application uses PDFium for rendering, QuickJS-NG for the original scripts, and one live JavaScript form state. It supports the tested initialization, editing/calculation, original class dialog, new-copy save and reopen workflows for both current sheets. Companion, wild-shape and spell generation pass the defined cases for both editions, including real Reader reopen/save. The 2024 wild-shape workflow uses an explicitly logged, user-approved runtime repair; original PDF scripts are preserved. Wider compatibility remains incomplete. Evidence and screenshots stay local under ignored `output/testing`.

## Implementation starting point

The original documentation baseline preceded the native implementation. Run `git log -5 --oneline` to see the focused baseline commits and `git status --short` to verify a clean working tree. The handoff identifies the harness commit and the next development milestone.
