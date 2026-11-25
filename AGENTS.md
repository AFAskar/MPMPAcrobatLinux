# Engineering & Agent Guidelines

## Core Constraints

- **Atomic commits:** Keep each commit focused on one cohesive change with a clear commit message.
- **Concrete verification:** Back every feature and fix with reproducible unit/integration tests.
- **Keep agent artifacts out of Git:** Session handoffs, compatibility audits, adversarial reviews, test logs, and generated evidence belong in agent-side artifacts or gitignored `output/` — never tracked under `docs/`.

## Local-Only Content & Privacy

- **Never commit paid MPMB PDFs or extracted scripts:** The reference MPMB PDFs are paid Patreon content. Keep them, personal character sheets, generated PDFs, logs, and VM checkpoints strictly local (`Testing/`, `output/`, `*.pdf` are ignored). `docs/fixtures.json` records filenames and integrity hashes only.
- **Preserve original fixtures:** Always run tests against unique disposable copies under `output/testing` (Linux) or `MPMB-Testing/runs` (Windows VM).
- **Local environment overrides:** Configure local Windows VM usernames, SSH keys, hosts, and Python paths via a gitignored `.env` file (copied from `.env.example`) or environment variables — never hardcode machine-specific details in tracked files.
- **Pinned submodule:** `2024_MPMBs-Character-Record-Sheet` is a pinned read-only reference submodule. Initialize with `git submodule update --init --recursive`; do not edit it or advance it implicitly.

## Native Reader Architecture Invariants

- **Single authoritative form state:** Keep QuickJS-NG (`src/runtime.rs` + `src/acrobat.js`) as the sole live form state. PDFium renders disposable flattened projections only and must not be used as a second form/JavaScript runtime.
- **Zero runtime script overrides:** Execute original embedded MPMB scripts verbatim to match Adobe Acrobat Reader behavior. Document upstream PDF script bugs rather than monkey-patching them at runtime.
- **Preserve MPMB `Array.prototype.find`:** Original MPMB scripts redefine `Array.prototype.find` as a regex/index lookup. Host JS and diagnostic probes must not assume standard `Array.prototype.find(predicate)` semantics after document scripts load.
- **Keep Acrobat API boundaries faithful:**
  - Keep canonical `/V`, raw rich spans, and formatted `/AP` display separate.
  - Keep `Field.value` and field-event `Event.value` conversions distinct.
  - Respect widget-local `/DA` and `/Q` before parent attributes; preserve non-leaf `/CO` calculation-order slots and named-template `/TemplateInstantiated` origins on spawned pages.
  - Preserve embedded-font priority and verify actual PostScript identity/glyph coverage before accepting any installed fallback face.
- **Controlled printing:** Printing tests must target controlled file destinations or cancel the dialog — never send automated jobs to a physical printer.
- **Resource bounds:** Keep Cargo builds single-job (`-j 1`, configured in `.cargo/config.toml`) on constrained hosts to avoid OOM alongside VMs.

## Windows Adobe Acrobat Reference Harness

Read `docs/testing-environment.md` before modifying or running Acrobat reference tests.

- Run `tools/acrobat/run preflight` and `tools/acrobat/run readiness` before treating a Windows Reader VM as an oracle.
- Serialize all operations and suites per Windows desktop; never queue competing suites on the same desktop.
- Execute MPMB commands through the adapter's application menu in the target document's context (`tools/acrobat/run control`), not from an external controller PDF or unverified fixed-coordinate macros.
- Freeze fingerprinted `tools/acrobat` inputs while a qualification run is active.
- Independently validate saved PDFs on Linux (`pypdf` canonical fields, widgets, appearance streams, decoded original scripts, and Poppler renders); never write expected oracle values with a PDF library.
- Retain failed probe diagnostics and close/retain failed documents cleanly instead of silently replaying mutations or hiding caught errors.
- If the local VM is managed-saved, resume with `tools/acrobat/run up`; restore checkpoints only while Windows is cleanly shut down.
