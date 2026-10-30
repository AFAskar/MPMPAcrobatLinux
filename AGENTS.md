# Constraints

- Atomic Commits
- Relevant Commit Messages Per atomic commit
- Concrete Proofs by testing Per Feature

# MPMB development environment

Read `docs/testing-environment.md` before changing or testing PDF behavior.

- Preserve the supplied PDFs under `Testing/` and at the repository root. Work on unique copies in the Windows `MPMB-Testing/runs` directory and local `output/testing`. `docs/fixtures.json` records original hashes.
- The Windows reference is real Adobe Acrobat Reader. Run `tools/acrobat/run preflight` and `tools/acrobat/run readiness` before treating it as an oracle. A failed suite is a failure; inspect its JSON evidence and screenshots.
- Use `tools/acrobat/run control` for serialized desktop and original MPMB JavaScript operations. Its `ready` check waits for document initialization and active calculations. Do not replace this with fixed coordinates or unverified SendKeys macros.
- MPMB commands must run through the adapter's application menu in the target document's context. Its timers and field events depend on that context. Do not call the document's functions directly from a controller PDF.
- Independently validate saved PDFs on Linux, including canonical fields, widgets, appearance streams and rendering. Never use a PDF library to write expected reference values into an oracle output.
- The reference MPMB PDFs are paid Patreon content. Never commit or redistribute the PDFs or extracted document scripts; do not force-add ignored fixtures.
- Keep private character data, generated PDFs, logs and VM checkpoints out of Git. The 2024 source checkout is reference material; the 2014 embedded scripts can be extracted with `tools/acrobat/run inventory`.
- If the VM is managed-saved, resume with `tools/acrobat/run up` and preserve the saved RAM/process state. Reconnect the harness and rerun preflight/readiness; do not discard managed-save state as routine startup.
- Restore a VM checkpoint only while Windows is cleanly shut down. The checkpoint tool retains pre-restore state.

- The 2024 source is a pinned reference submodule. Initialize with `git submodule update --init --recursive`; do not edit it or advance it with `git pull`/`--remote`. Deliberate reference upgrades require a separate parent-repository commit.

# Native reader implementation

- Keep Cargo builds at one job and serialize Acrobat operations. The Windows VM has 4 GiB RAM; do not spawn parallel agents for this work.
- Keep QuickJS as the single authoritative form state. PDFium renders disposable projections; its built-in execDialog is a successful no-op and is not an alternative MPMB runtime.
- Compatibility means all reachable MPMB workflows in all three authorized fixtures. Base-class level/proficiency checks, default dialog replies and passing smoke tests do not establish full compatibility. Record unsupported behavior and coverage gaps explicitly.
- Separate implementation into milestones with concrete native and real Acrobat evidence before marking each milestone complete. Maintain docs/native-compatibility.json, docs/mpmb-compatibility-audit.md and docs/development-handoff.md.
- Runtime repair mpmb-2024-261023-wildshape-pop-typo is already user-authorized. Keep its exact fingerprint/source guards, diagnostics/UI disclosure, unchanged embedded script bytes and strict-original-scripts option. Do not request authorization again for this repair.
- Printing tests must use controlled file destinations or cancel the printer dialog; never automatically send test jobs to a physical printer.
- Original MPMB scripts redefine `Array.prototype.find` as a regex/index lookup. Preserve that behavior. Native host code and probes must avoid assuming standard `find(predicate)` semantics after document scripts load.
- Freeze the fingerprinted reference-harness inputs while qualification runs; see `docs/testing-environment.md`. Editing `tools/acrobat` source during readiness invalidates the entire suite, even when workflow cases passed.
- Run reference suites one at a time through completion and cleanup; do not queue multiple desktop suites. Each suite must reject a pre-existing document before opening its disposable copy. A failed suite must retain/close its own document before another suite starts.
- Scripted test replies must be valid controls/buttons offered by the actual dialog. Alert code 1 is OK, not Yes; Yes/No uses 4/3. Sidekick conversion requires explicit confirmation and base-creature hit dice; generic defaults do not exercise that class.

- Diagnostics transported through a PDF text field must use ASCII-escaped JSON (or independently prove equivalent encoding). Include a Unicode sentinel and verify the saved field against a Reader code-unit/checksum summary; unescaped Unicode can be altered by the transport field itself.
- Diagnostic event observers must catch unavailable-property getter errors locally. Letting logging throw from an original field action changes the behavior being measured; record the getter error without interrupting the event.

- Keep canonical /V, raw rich spans and formatted display separate. Record comparison normalization explicitly; a check that ignores properties is not exact API equality. Reassigning copied rich colors can requantize them in Reader.
- Qualify emitted rich XML in real Reader, including version attributes. Native parsing/rendering of its own output alone does not establish interoperability.

- Respect widget-local /DA and /Q before parent field attributes when loading styles. Reader can leave the parent's /DA unchanged while saving new styles on widget zero, even when that widget belongs to an inactive template. Keep /DS defaults, widget appearance defaults and existing rich spans separate; changing defaults does not restyle existing spans.

- Rich layout metrics are not interchangeable: measured first baselines use the widget-default font's PDF bounds, while later leading uses run-font typographic metrics. Qualify changes against saved Reader appearances, including mixed sizes and default/explicit spacing; do not hardcode expected coordinates. Host-layout probes that clear field actions are isolated diagnostics, not original MPMB workflow passes.

- Save/reopen qualification must include subsequent edits through original field actions that regenerate appearances. An unchanged resave can retain old appearances and hide missing renderer or font support. Test embedded-face portability with system-font command lookup disabled during fresh native probes.
- Fontconfig can successfully return an unrelated substitute. Verify actual PostScript identity and glyph coverage before claiming a requested face, and retain embedded-font priority.

- Read live cross-process Windows edit contents with bounded `WM_GETTEXT`, not cached `GetWindowText` captions. Empty UIA children or abbreviated owner-drawn combo strings do not prove empty/full option lists. Keep numeric combo state separate from exact offered labels. Select editable controls by observed type, ownership and role; the first class-dialog edit is the numeric level, not the class name.
