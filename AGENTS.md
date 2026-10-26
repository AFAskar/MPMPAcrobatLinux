# MPMB development environment

Read `docs/testing-environment.md` before changing or testing PDF behavior.

- Preserve the supplied PDFs under `Testing/` and at the repository root. Work on unique copies in the Windows `MPMB-Testing/runs` directory and local `output/testing`. `docs/fixtures.json` records original hashes.
- The Windows reference is real Adobe Acrobat Reader. Run `tools/acrobat/run preflight` and `tools/acrobat/run readiness` before treating it as an oracle. A failed suite is a failure; inspect its JSON evidence and screenshots.
- Use `tools/acrobat/run control` for serialized desktop and original MPMB JavaScript operations. Its `ready` check waits for document initialization and active calculations. Do not replace this with fixed coordinates or unverified SendKeys macros.
- MPMB commands must run through the adapter's application menu in the target document's context. Its timers and field events depend on that context. Do not call the document's functions directly from a controller PDF.
- Independently validate saved PDFs on Linux, including canonical fields, widgets, appearance streams and rendering. Never use a PDF library to write expected reference values into an oracle output.
- The reference MPMB PDFs are paid Patreon content. Never commit or redistribute the PDFs or extracted document scripts; do not force-add ignored fixtures.
- Keep private character data, generated PDFs, logs and VM checkpoints out of Git. The 2024 source checkout is reference material; the 2014 embedded scripts can be extracted with `tools/acrobat/run inventory`.
- Restore a VM checkpoint only while Windows is cleanly shut down. The checkpoint tool retains pre-restore state.
