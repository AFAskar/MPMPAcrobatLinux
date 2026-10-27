# Implementation handoff

## Continuation update — 2026-10-27

The goal remains active and incomplete. See [implementation-milestones.md](implementation-milestones.md) for acceptance work split into printing, source/class/subclass selection, real table workflows, and persistence/presentation.

Native printing now implements the dependencies used by the original PrintTheSheet and PrintButton. Doc.print synchronously captures authoritative state, projects a disposable copy, imports selected pages into a new PDFium document, flattens with print visibility, strips interactive structures, and creates a new output. The desktop destination flow offers PDF output or explicitly confirmed CUPS submission. Probe printing requires an explicit print_output_dir. Advanced unsupported print parameters fail. Physical printing has not been tested.

The original print dialog exposed a missing execDialog.destroy callback. It now runs after commit, cancellation and custom dialog endings. Print-only fields also receive updated appearances. Original embedded scripts remain unchanged. PDFium instance lifetime is reference-counted so synchronous printing does not shut down the desktop renderer.

Concrete native evidence: `output/testing/native-printing-1793074562899703807/printing.json` passes all three fixtures and twelve print artifacts, checking all/selected/generated pages, simplex/long-edge duplex, cancellation, all four display states, static PDF structure/text/rendering, original script retention and interactive native reopen. The first sentinel design triggered actual class/race processing and was replaced with plain attack-description widgets; earlier failed runs remain retained. `output/testing/native-acceptance-1793074626929747931/acceptance.json` passes both current sheets after the dialog change. Twenty-five Rust tests, formatting and strict clippy pass at this stage.

The printing milestone is still in progress: real Reader printed-file output comparison remains unqualified. All three native interactive print outputs have since passed actual Reader print-dialog cancellation and Reader save with independent comparisons: `output/testing/native-printing-1793074562899703807/reader-printing-1793075547563190782/reader-printing.json`. Reader enum inspection established interaction levels 0/1/2 and duplex values 1/2/3; the host now uses these numeric constants. The fresh numeric-constant native suite passes under `output/testing/native-printing-1793075666647821266/printing.json`. The actual Linux destination dialog passed named AT-SPI inspection and cancellation on both current sheets, with screenshots inspected: `output/testing/native-print-desktop-1793074958381478234/desktop.json`. An initial screenshot-tool failure on Wayland is retained separately; the suite uses Spectacle for this desktop. The first fresh readiness run failed because an old disposable Reader document was left open, and the checked close correctly refused a multi-document shutdown. That failure is retained as `output/testing/readiness-1793074115.json`. After inspecting the actual save prompt and closing the stale disposable session, the print-capable application-menu adapter was deployed; fresh 27-check preflight and 24-case readiness passed (`output/testing/readiness-1793074448.json`). The earlier failure remains retained separately.

Dropdown/source audit tooling is now available as `tools/native/subclass-audit`. The 2024 Fighter/Champion pilot passed five progression checkpoints and native PDF reopen (`output/testing/native-subclasses-1793074776109531946/subclasses.json`). The broad 2024 run is in progress under `native-subclasses-1793074818475225818`; consult its JSON rather than assuming completion. It includes all sources/class elements through original dialog buttons and selects actual offered dropdown labels. Shadowed/excluded definitions, command-filtered cases and subclasses not exercised are recorded. Feature-choice replies remain default-only and do not establish feature completeness. The new selection helper has a focused rejection test; 26 Rust tests and strict clippy pass.

Native bookmarks now fix the original `functionBookmarks` missing-setAction failure (retained counterexample: `output/testing/bookmark-counterexample-1793075189535747011/report.json`). `tools/native/bookmarks` passes all three fixtures (`native-bookmarks-1793075341660271078/bookmarks.json`), including original createBookmarks/functionBookmarks, action target context, removal, styles/colors/open counts, independent outline structure and original script checks, native save/reopen and retained actions. `native-bookmark-desktop-1793075616698542936/desktop.json` captures both real panels and post-action navigation renders; captures were inspected. Direct destination zoom/position remains partial and is diagnosed; unresolved/named and other unsupported action kinds fail explicitly. Changed bookmark trees still need Reader roundtrips.

The broad all-source 2024 subclass run stopped at its first actual failure after 35 passing cases: Circle of Wildfire assigns undefined to a generated companion hit-die field, then FormatHD fails in the native host. Evidence is `native-subclasses-1793074818475225818/2024-35-report.json`; the aggregate suite is a failure, not a pass. `wildfire-debug-1793076223508441997` records the assignment from original ApplyCompRace. A Reader comparison is being prepared to determine correct field coercion. The run spanned native development builds; individual cases are diagnostic evidence, not qualification of one frozen binary.

The first actual Microsoft Print to PDF pilot confirmed the selected virtual printer through a fresh screenshot and OCR, but the generic clipboard helper focused the underlying PDF rather than the Save Print Output As edit. The print was cancelled, and its disposable state is retained under `print-printer-pilot-1793075763799596680`. This failed pilot must not be counted as printed-output evidence. A scoped native file-picker write/read-back operation is needed for reliable virtual-printer output; no physical printer was selected.

## Native implementation update — 2026-10-26

A runnable Rust desktop application now opens and renders both supplied editions, executes their original 25/27 document scripts, edits fields and runs dependent calculations, handles the original class dialog, saves disposable copies, and reopens them natively and in real Windows Reader. See [native-reader.md](native-reader.md) for commands and architecture, and [native-compatibility.json](native-compatibility.json) for measured coverage. Full MPMB compatibility remains incomplete.

PDFium was inspected first: its `execDialog` is a successful no-op and the public embedding interface cannot replace the needed Acrobat object model. PDFium therefore only renders temporary projections. QuickJS-NG owns the single authoritative form state. lopdf 0.46 preserves the input graph and projects values, widget appearances, changed actions, calculation order and a structural page journal. Earlier lopdf versions selected stale compressed objects in the incrementally saved regression character; do not downgrade without that regression.

The native application includes field selection/editing, PDF widget actions and checkbox toggles, original native class/source/spell dialogs, toolbar commands and hierarchical popup menus, local UTF-8 script imports, new-copy saving and a close-save confirmation. Basic rich spans, alignment, wrapping and choice labels render in embedded Unicode appearances. Normal button icons use original PDF resources. Exact fonts, complete rich text, all dialog controls/layouts, bookmark persistence, template overlay, URL/binary imports, printing/export and the document `saveAs` API remain gaps.

Both editions pass original wolf companion generation, wolf wild-shape generation, and Druid spell generation. All six outputs pass native save/reopen, independent canonical field/widget/appearance/script checks, and real Reader reopen/save. The generated page tree preserves inherited resources, field ancestors, renamed/shared logical fields, widgets and original calculation entries. Reader's canonical names require ASCII wrapper `/T` names; UTF-16 wrapper names caused a retained failed Reader run before the fix.

The user explicitly authorized repair `mpmb-2024-261023-wildshape-pop-typo`. It replaces incorrect `pop` reads with the local `prop` in the loaded runtime function only, guarded by the exact Functions2 fingerprint and expected source markers. Original embedded script bytes are preserved. Diagnostics and the UI disclose the repair. `MPMB_STRICT_ORIGINAL_SCRIPTS=1` or `--strict-original-scripts` retains the original failure; a fresh strict probe confirms the failure and an empty repair list. This repaired workflow is not strict original-script compatibility.

Imports and the supplied Ashnar regression also pass native execution, save/reopen, complete imported-payload retention and remembered-spell retention. A prior real Reader roundtrip passed for Ashnar. All 4,241 canonical values in the fresh native Ashnar output match its real-Reader saved counterpart; original embedded scripts match as well. Full comparison evidence is `native-validation-1793047420184139528/ashnar-comparison.json`. Its private values and source scripts remain local. A new lifecycle suite hides/reveals a shared page, removes/readds a companion, preserves character data, and saves/reopens a changed Calculate action and calculation ordering on both editions. The earlier additional Reader run failed at a read-only global desktop lock. After access was restored and the reference was freshly qualified, both lifecycle/action cases passed actual Reader reopen/save; the earlier failure remains preserved separately.

Fresh validation: 23 focused Rust tests, `cargo fmt --check`, and `cargo clippy --locked -- -D warnings` pass. Native desktop smoke opens actual reader/class-dialog windows for both editions; their captures were inspected. Builds use one job. No parallel agents were used.

Current ignored evidence under `output/testing/`:

- Oracle qualification: `readiness-1793046363.json` (24/24), `class-audit-up.log` and `class-audit-preflight.log` (27/27).
- Native milestone: `native-acceptance-1793047033548639856/acceptance.json`; fresh Reader milestone pair: `native-validation-1793047420184139528/base-acrobat.json`.
- Generated workflows: `native-generated-1793039821424735227/generated.json` and `generated-acrobat.json` (six native and six real Reader passes).
- Full generated comparisons: `native-generated-1793039821424735227/full-comparisons.json` and per-case comparison JSON/PNG files. All 2014 canonical values match Reader. Each 2024 case differs in `CurrentEvals.Stringified`. Page/widget counts and embedded scripts match. Two hidden widgets per case differ only in the Print flag. Some Reader-regenerated appearance content and rendered pixels differ; appearance identity is not claimed.
- Imports/Ashnar: `native-extended-1793046987407518666/extended.json`; fresh Ashnar Reader evidence is linked by `native-validation-1793047420184139528/validation.json`.
- Page lifecycle and changed-action persistence: `native-lifecycle-1793040281629132421/lifecycle.json`; fresh qualified Reader run: `native-lifecycle-1793040281629132421/acrobat-1793047420204771017/generated-acrobat.json`. The older `generated-acrobat.json` and `native-lifecycle-actions-acrobat-run.log` retain the prior infrastructure failure.
- Actual desktop captures: `native-desktop-1793040011023215282/`.
- Strict original 2024 failure: `native-strict-1793045376527449608/expectation.json`.

Repository and reference access have been restored. The pending action-persistence fix is committed as `1875724`, the core regressions as `58e588d`, the generated/lifecycle regressions as `49ecb23`, and the source-derived class/scope audit as `62badfa`. They follow the five original focused implementation commits. The earlier sandbox-blocked oracle attempt remains retained failure evidence; it must not be counted as a pass.

The user's clarified acceptance target is **all MPMB behavior in all three supplied paid PDFs**, including any predefined class and real table usage. General Acrobat JavaScript completeness is not the target. This goal remains **not achieved**. The new [MPMB audit](mpmb-compatibility-audit.md) records 38 passing base-class fixture cases at six levels (228 checkpoints), 19 excluded/ambiguous definitions not exercised, and unexercised subclass/feature/table workflows. The original MPMB print workflow demonstrably fails in all three PDFs because its required print APIs are absent. Do not turn a passing milestone or base-class progression smoke into a full-compatibility claim.

The historical environment-only baseline below describes the earlier starting point.

## Historical environment baseline

Prepared on 2026-10-26 (UTC+3). The qualified Acrobat harness is committed as `04ef77a` (`feat(testing): add qualified Windows Acrobat reference harness`). The initial documentation baseline is `94d0a26`; submodule registration is `6ffa46f`. The latest documentation commit is the current implementation starting HEAD; identify it with `git rev-parse HEAD`. Its scope is the testing environment, not a native reader implementation.

## Current state

- Fedora development tools and the Windows Reader bridge are available locally. The VM uses 4 vCPUs, 4 GiB RAM and Reader 26.2.22031.0 with protocol 3.
- Qualification: 27/27 preflight, 24/24 readiness, 2/2 real file imports and 6/6 post-restart stability cases passed. The clean checkpoint was actually restored and boot-verified.
- After the internet interruption, a fresh 27-check preflight and a 225.892-second smoke passed. All 15 qualified output PDFs and three original fixtures retained their hashes; the interval audit found no new Reader crashes, guest resource exhaustion or host OOM kills.
- No Cargo workspace, native desktop application, PDF engine integration or native compatibility layer exists yet.

Local evidence is intentionally excluded from Git: `output/testing/qualification-final.json`, `output/testing/connectivity-recheck-1793015176.json`, and the run reports referenced by the readiness audit. A fresh clone needs authorized local fixtures and a configured VM; these are not bundled or downloaded automatically. Existing ignored files on this machine are preserved.

## Source reference

`2024_MPMBs-Character-Record-Sheet/` is a Git submodule pinned to upstream commit `5d6e57c861643ca77764131bd5dc865389879667`. Initialize it with `git submodule update --init --recursive`; confirm its revision with `git submodule status`. The existing local checkout was reused without source changes. No upstream commits are imported into the parent repository’s history.

Treat this checkout as reference-only. Do not edit, commit inside it, or pull a newer revision during ordinary development. A deliberate reference upgrade should update the gitlink in its own parent-repository commit and document the new revision. Public upstream source and locally extracted document scripts are separate: the latter stay under ignored output paths. Paid PDFs remain excluded.

## Before changing PDF behavior

Read AGENTS.md and testing-environment.md. Verify the live environment:

```bash
tools/acrobat/run up
tools/acrobat/run smoke
```

Before accepting new oracle results, run preflight and the readiness suite as required by AGENTS.md. Use unique run copies, serialize desktop operations, and independently validate saved outputs. Keep paid PDFs and extracted source local. Do not add them with `git add -f`.

## First development milestone

Inspect the original source and evaluate the PDF engine before committing to an architecture. PDFium is the provisional first candidate; enabling its JavaScript support alone does not provide all MPMB-required Acrobat APIs. Rust may use native PDF/JavaScript dependencies. Keep one authoritative form state and track unsupported APIs explicitly.

Implement a runnable vertical slice that:

1. Opens and renders both local 2014 and 2024 sheets.
2. Executes their original initialization scripts.
3. Supports field editing and dependent calculations.
4. Handles an actual MPMB character-selection dialog.
5. Saves a disposable PDF that reopens correctly in the native application and real Windows Acrobat.

Then extend coverage to companion and wild-shape pages, spell generation, imports and the supplied filled-character regression. Use reference-feature-inventory.json as an initial inventory, not an exhaustive compatibility specification. Compare fields, widgets, appearance streams, embedded scripts, generated pages and saved character state. Stubs and silently ignored errors do not establish compatibility.

Add reproducible native build/run instructions as implementation begins. Keep Rust source and Cargo.lock tracked, generated artifacts ignored, and changes in focused commits. Avoid concurrent large builds or parallel desktop tests on this laptop.

## Baseline checks

The initial commits were checked for Python syntax, shell syntax, JavaScript syntax, valid JSON, staged whitespace, unwanted binary/private artifacts and common credential patterns. Ignore rules were checked against both excluded paths and trackable Rust/source/example files. Functional harness evidence predates these commits; the harness source is unchanged from the qualification fingerprint.

See testing-readiness-audit.md for measured acceptance boundaries and retained failure history; see windows-reference-benchmark.md only for the retired app-server/direct macro comparison.
