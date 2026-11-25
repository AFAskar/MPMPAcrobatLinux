# Native Reader Architecture & Development

MPMB Reader is a native Rust desktop application built to execute original MorePurpleMoreBetter (MPMB) interactive PDF character sheets without Adobe Acrobat Reader. Original paid PDFs and extracted scripts remain strictly local and gitignored.

## Build and Run

Linux prerequisites: Rust/Cargo, a C toolchain, X11 or Wayland dev headers, OpenGL/Mesa, `zenity` (file picker), Poppler, and DejaVu Sans fonts.

```bash
tools/native/setup-pdfium
cargo build --locked
cargo run --locked -- "Testing/<authorized sheet filename>.pdf"
cargo test --locked
tools/native/acceptance
tools/native/extended
tools/native/generated
tools/native/lifecycle
```

- `tools/native/setup-pdfium` downloads the pinned Linux x64 PDFium distribution (`chromium/8111`), checks its SHA-256, and retains third-party licenses under ignored `output/deps`. PDFium's V8 runtime is unused.
- `MPMB_PDFIUM` overrides the shared-library path; `MPMB_FONT` overrides the Unicode appearance font.
- Default DejaVu Sans discovery checks standard Linux locations and Fontconfig, verifying the actual TrueType PostScript identity instead of accepting unrelated substitutes.
- `.cargo/config.toml` sets one build job and disables debug symbols in dev builds.

### Desktop UI

The desktop UI (`src/ui.rs`, `src/ui/theme.rs`, `src/ui/state.rs`) provides:

- **Dark (Obsidian Slate & Gold, default)** and **Light (Ivory & Ink)** themes (`MPMB_THEME=dark|light` or toolbar toggle, propagated to modal dialogs).
- Revision-keyed `ProjectionCache` to avoid redundant per-frame PDF projection and widget JSON recomputation.
- `ZoomState` with Fit-Width and quantized manual zoom (`Ctrl+Scroll`, `Ctrl+-`/`=`/`0`), plus keyboard shortcuts (`Ctrl+S`, `Ctrl+B`, `PageUp`/`PageDown`).
- Top command bar (`Classes…`, `Tools`, `Sheets`, `Save…`, theme toggle, clean/unsaved status pill) and collapsible left sidebar with **Character Quick-Card**, searchable/filterable **Fields** + Field Inspector (`Ctrl+Enter` apply, `Esc` discard), **Bookmarks**, and **Diagnostics** tabs.
- Interactive canvas widget overlays for field selection, checkbox toggling, and original button actions. Read-only fields and pushbuttons disable text/choice editing; uncommitted drafts can be discarded without affecting prior committed edits.
- Atomic non-destructive saves: existing paths (including originals) are never overwritten silently.

## Architecture

PDFium's built-in `CJS_App::execDialog` is a no-op and does not expose replacing the Acrobat JS object model. MPMB Reader separates responsibilities cleanly:

- **`src/pdf.rs` (+ `src/pdf/*`):** `lopdf` reads canonical `/T` hierarchies, widget geometry, inherited attributes, additional actions (`/AA`, `/A`), `/CO`, metadata, bookmarks, and embedded document scripts. Saves project live QuickJS form state into a cloned PDF graph with updated values and appearance streams while preserving untouched scripts and object graphs.
- **`src/acrobat.js`:** Single authoritative live form state, document globals, events (`Keystroke`/`Validate`/`Calculate`/`Format`/`Focus`/`Blur`), timers, menu registry, dialog lifecycle, and serialization. Original embedded scripts execute verbatim in PDF name-tree order.
- **`src/runtime.rs`:** Bounded-memory QuickJS-NG (`rquickjs`), synchronous native callbacks, and explicit error reporting. No original MPMB source is vendored into the executable.
- **`src/render.rs`:** PDFium renders disposable flattened projections so widget appearances render accurately without instantiating a second interactive form runtime.
- **`src/ui.rs`:** `eframe`/`egui` desktop UI and separate native modal dialog process preserving synchronous `execDialog` call stacks.

## Diagnostic CLI & Test Suites

```text
mpmb-reader sheet.pdf --probe scenario.json report.json
mpmb-reader sheet.pdf --desktop-smoke output/testing/unique-desktop-directory
```

- Probe scenarios specify explicit `dialogs` replies, numeric `alerts`, and `steps` (`advance`, `edit`, `user-edit`, `eval`, `assert`, `render`, `save`). Unanswered prompts and unsupported APIs fail explicitly.
- `MPMB_TRACE_FIELDS='Character Level'` logs initial values and script assignment stacks to stderr for debugging (keep private traces under gitignored `output/testing`).
- `tools/native/acceptance`, `extended`, `generated`, `lifecycle`, `table-workflows`, `bookmarks`, `attachments`, `printing`, `fighting-styles`, `class-audit`, `subclass-audit`, and `sidekicks` run reproducible native checks against unique disposable copies under `output/testing`.
- `tools/native/compare.py` and `tools/native/compare-state` compare canonical field values, widgets, appearances, decoded original document scripts, and `.Stringified` expressions between native and Adobe Acrobat Reader outputs.
- `tools/native/verify-acrobat.py` reopens native outputs in a qualified Windows Adobe Acrobat Reader VM and independently verifies the saved PDF on Linux.
- `tools/native/compatibility.py` writes a static API inventory report to gitignored `output/testing/native-compatibility.json` (configurable via `--output`).

## Strict Original-Script Execution

Original embedded MPMB scripts execute verbatim with **zero runtime overrides** (`repairs: []`). Upstream script defects in specific sheet builds (such as the 2024 `v24.2.0+261023` `ApplyWildshape` `ReferenceError` and `format2()` plain-string `countDecimals()` `TypeError`) are reproduced faithfully rather than monkey-patched.

## Explicit Boundaries & Security Model

- **Trusted-input boundary:** Do not deploy the desktop reader as a sandbox for untrusted arbitrary PDFs. QuickJS memory/stack limits and bounded file-import caps (16 MiB JS, 64 MiB XFDF) are enforced, but document scripts can pass local filesystem paths to the file bridge and JavaScript runs synchronously in the UI process without an execution-time interrupt. Intended strictly for trusted local MPMB sheets and user-approved add-ons.
- **Fonts & appearances:** Rich appearances prefer original embedded TrueType faces and reuse saved Type0 appearance font programs across saves, with `MPMB_FONT` / DejaVu Sans as Unicode fallback. Proprietary fonts are not shipped; CFF installed faces and nonzero font-collection members are not supported by installed-font lookup.
- **Acrobat-Pro-only APIs:** Authoring/Pro-only APIs unreachable in Adobe Acrobat Reader (`MPMBImportPage`, `exportAsXFDF` file write, `importAnFDF`, authoring `Template.hidden`/`extractPages`/`createTemplate`, multi-document `app.openDoc`) remain outside Reader-parity scope.
- **Printing & attachments:** Printing tests must use controlled file destinations (`print_output_dir`) or cancel the dialog. Attachment exports require `attachment_output_dir` in probes and never overwrite existing paths.
- **Usage-rights signatures:** Full-file PDF serialization may invalidate Adobe usage-rights signatures; Reader reopen/save roundtrips are used to verify interoperability.
