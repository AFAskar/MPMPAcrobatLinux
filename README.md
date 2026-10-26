# Linux-native MPMB reader

The goal is a native Rust PDF reader that executes the original MPMB scripts with Acrobat-compatible behavior. This initial repository contains the qualified testing environment and development handoff. The native reader has not been implemented yet.

Start with [AGENTS.md](AGENTS.md), the [development handoff](docs/development-handoff.md), and the [Acrobat environment guide](docs/testing-environment.md).

## Local reference environment

Development runs on Fedora. Real Adobe Acrobat Reader runs in a local Windows VM with 4 vCPUs and 4 GiB RAM. The direct test harness uses localhost SSH and requires no API key or additional Windows model turn.

```bash
tools/acrobat/run up
tools/acrobat/run smoke
```

The recorded qualification passed 27 preflight checks, 24 readiness cases, two file-import cases and six stability cases. See the [readiness audit](docs/testing-readiness-audit.md) for scope, evidence and limitations. Recheck the live environment before development tests.

## Local-only content

The MPMB reference PDFs were acquired as paid Patreon content. They are not included or licensed for redistribution by this repository. Keep them, saved characters, generated PDFs and extracted document scripts local. Obtain your own authorized copies; `docs/fixtures.json` records expected filenames and integrity hashes only.

The local 2024 reference checkout, generated evidence under `output/`, VM state, credentials and build outputs are also ignored. The small synthetic sentinel under `Testing/addons/` is test instrumentation, not an MPMB sheet.

## Implementation starting point

The documentation commit containing this file is the implementation starting HEAD. Run `git log -3 --oneline` to see the focused baseline commits and `git status --short` to verify a clean working tree. The handoff identifies the harness commit and the next development milestone.
