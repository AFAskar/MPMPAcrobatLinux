# Implementation handoff

## Continuation update — 2026-10-27

The goal remains active and incomplete. See [implementation-milestones.md](implementation-milestones.md) for acceptance work split into printing, source/class/subclass selection, real table workflows, and persistence/presentation.

Native printing now implements the dependencies used by the original PrintTheSheet and PrintButton. Doc.print synchronously captures authoritative state, projects a disposable copy, imports selected pages into a new PDFium document, flattens with print visibility, strips interactive structures, and creates a new output. The desktop destination flow offers PDF output or explicitly confirmed CUPS submission. Probe printing requires an explicit print_output_dir. Advanced unsupported print parameters fail. Physical printing has not been tested.

The original print dialog exposed a missing execDialog.destroy callback. It now runs after commit, cancellation and custom dialog endings. Print-only fields also receive updated appearances. Original embedded scripts remain unchanged. PDFium instance lifetime is reference-counted so synchronous printing does not shut down the desktop renderer.

Concrete native evidence: `output/testing/native-printing-1793074562899703807/printing.json` passes all three fixtures and twelve print artifacts, checking all/selected/generated pages, simplex/long-edge duplex, cancellation, all four display states, static PDF structure/text/rendering, original script retention and interactive native reopen. The first sentinel design triggered actual class/race processing and was replaced with plain attack-description widgets; earlier failed runs remain retained. `output/testing/native-acceptance-1793074626929747931/acceptance.json` passes both current sheets after the dialog change. Twenty-five Rust tests, formatting and strict clippy pass at this stage.

The printing milestone is still in progress: real Reader printed-file output comparison remains unqualified. All three native interactive print outputs have since passed actual Reader print-dialog cancellation and Reader save with independent comparisons: `output/testing/native-printing-1793074562899703807/reader-printing-1793075547563190782/reader-printing.json`. Reader enum inspection established interaction levels 0/1/2 and duplex values 1/2/3; the host now uses these numeric constants. The fresh numeric-constant native suite passes under `output/testing/native-printing-1793075666647821266/printing.json`. The actual Linux destination dialog passed named AT-SPI inspection and cancellation on both current sheets, with screenshots inspected: `output/testing/native-print-desktop-1793074958381478234/desktop.json`. An initial screenshot-tool failure on Wayland is retained separately; the suite uses Spectacle for this desktop. The first fresh readiness run failed because an old disposable Reader document was left open, and the checked close correctly refused a multi-document shutdown. That failure is retained as `output/testing/readiness-1793074115.json`. After inspecting the actual save prompt and closing the stale disposable session, the print-capable application-menu adapter was deployed; fresh 27-check preflight and 24-case readiness passed (`output/testing/readiness-1793074448.json`). The earlier failure remains retained separately.

Dropdown/source audit tooling is now available as `tools/native/subclass-audit`. The 2024 Fighter/Champion pilot passed five progression checkpoints and native PDF reopen (`output/testing/native-subclasses-1793074776109531946/subclasses.json`). The broad 2024 run is in progress under `native-subclasses-1793074818475225818`; consult its JSON rather than assuming completion. It includes all sources/class elements through original dialog buttons and selects actual offered dropdown labels. Shadowed/excluded definitions, command-filtered cases and subclasses not exercised are recorded. Feature-choice replies remain default-only and do not establish feature completeness. The new selection helper has a focused rejection test; 26 Rust tests and strict clippy pass.

The first frozen 2024 run again stopped after 35 cases, but its Wildfire HP assertion was a probe bug: original MPMB scripts replace Array.prototype.find with a regex/index lookup, so the callback-style selector returned -1. The underlying companion already had 20 HP. The selector and the native multi-widget focus helper now avoid standard find assumptions. Original prototype behavior is preserved. The derived-value Wildfire case passes with 20 HP/blank hit dice plus five progression/native persistence checkpoints: `output/testing/native-subclasses-1793078338546766086/subclasses.json`. A focused unit simulates the overridden find and verifies field navigation. Both failed broad runs remain failures and do not cover later subclasses.

Six native table cases now pass (`output/testing/native-table-1793077542685557772/table.json`): Fighter/Champion and Monk/Shadow level 5 in each fixture, resource use, short/long rests, healing/hit-dice recovery, saved canonical values, appearances and native reopen. Independent Reader scenarios are prepared but not yet qualified. The verifier now handles `/Opt` display labels while keeping export values strict and enumerates inactive named-template widgets. Its valid baseline plus three damaged negative controls pass in `output/testing/verify-regressions-1793077970606239902/verification.json`. Earlier failed table runs remain retained; their failures revealed verifier limitations rather than permission to ignore them.

The print-output picker operation and additional original rest/source calls are deployed, but `readiness-1793076904.json` is a **failed** qualification: all 23 functional workflows passed, then the harness-integrity check rejected edits to verify.py made during the run. The resource audit did not run past that assertion, so it is not evidence of no new crash/OOM. Harness files are now frozen and `output/testing/continuation-frozen-harness-readiness.log` points to the replacement qualification. Do not edit fingerprinted harness inputs while it runs. All new Reader work waits for its complete pass.

The Circle of Wildfire failure is repaired in the host: undefined assignments normalize to an empty field before original Format events. No original script is patched. A real Reader run of the original class application confirms blank companion hit-die/level fields and 20 HP at Druid level 3 (`output/testing/wildfire-reader-seed-1793076325066121626/reader.json`); null assignment separately produces the literal text "null" and must not be treated as the same coercion. The targeted five-checkpoint Wildfire progression/native persistence suite now passes (`output/testing/native-subclasses-1793076845409009075/subclasses.json`). New subclass audits freeze the executable and record its hash, support a subclass filter and assert Wildfire's initial companion HP/blank hit dice. A full frozen 2024 rerun is underway in the path named by `output/testing/continuation-subclasses-frozen-2024.log`. Broader field coercion remains to be probed in Reader. Thirty-one Rust tests and strict clippy pass.

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

## Continuation: widget flags and newly exposed failures

Per-widget annotation flags are retained in the authoritative state and saved PDF, including indexed display assignments and template cloning. Fresh two-edition native acceptance and Reader saves pass: `native-acceptance-1793081175283634562`, `native-acrobat-1793081649617013956.json`; complete active-widget flags/geometry/states match Reader (`widget-final-native-{2014,2024}.json`). 2014 canonical values all match; the known 2024 CurrentEvals representation difference remains. Older native-seeded reference files already contained stripped flags and are insufficient fidelity baselines.

The frozen 2024 subclass run `native-subclasses-1793079112063681221` remains FAILED: it reached Hexblade, saved its progression state, then reopening failed in original SetRichTextFields on a missing companion skills field. Inspect this generated-page/removal state before extending coverage claims. Default feature replies and no independent Reader class qualification remain explicit limitations.

## Field commit/coercion correction

Actual Reader probes showed script assignments run commit Keystroke before Validate, both with string event values; rejected keystrokes retain the field value. Null/undefined become literal text unless field actions reject them. Arrays/objects assigned to text fields stringify before snapshot. This supersedes the provisional generic undefined-to-empty repair. Incorrect array persistence had saved `Template.extras.AScomp` as JSON text and broke Hexblade reopen.

Qualified exact native/Reader setter, coercion, formatting and calculation-rejection traces: `field-events-1793082876778218795/events.json` (clean Reader save/close). Boundary trace native replay `field-events-1793082700823705882` agrees with measured Reader, but the earlier expanded Reader suite failed close after a queued suite opened another document; retain that failure. Do not queue reference suites. New probes reject a pre-existing document at entry. Partial table scenario and other disposable files were retained before clean Reader shutdown.

Regressions after the correction: 35 Rust tests and strict clippy pass; native acceptance `native-acceptance-1793082350792331351`, all six table cases `native-table-1793082877958892618`, all three printing fixtures `native-printing-1793082799007399331`. Targeted Hexblade `native-subclasses-1793082229270078667` and Wildfire `native-subclasses-1793082187243630120` pass. Remaining Warlock/Wizard slice `native-subclasses-1793082304040159913` passed with its frozen earlier event candidate; this is default-choice progression/persistence, not Reader-equivalent feature qualification.

## Existing embedded-file export

Implemented EmbeddedFiles metadata and byte extraction, dataObjects/getDataObject, and exportDataObject for MPMB's original FAQ/helper workflows. Native chooser/save is implemented; PDF opening uses the desktop opener and runtime-owned temporary files. Non-PDF launching is rejected; probe launch requests are explicitly suppressed. Exact exported payloads, FAQ rendering, original scripts/field inventory, attachment persistence and native reopen pass all three fixtures: `native-attachments-1793100475546677964/attachments.json`. Its frozen binary predates the final read-only metadata getter; the getter has an independent descriptor-mutation regression test. 38 Rust tests and strict clippy pass. Reader metadata/menu/persistence tooling is prepared, but not yet run; desktop chooser/opening also remains unqualified. Attachment import/modification remains unsupported. No embedded attachment/script bytes were committed.

The VM was explicitly reported managed-saved during a later continuation. `tools/acrobat/run up` resumed it without discarding saved state and passed 27 preflight checks. The in-flight print comparison failed before opening a reference document due to SSH connection refusal (`native-printing-1793082799007399331/reader-print-output-1793100023077391216`). A fresh readiness run is in progress under `continuation-resumed-readiness.log`; retain its eventual JSON before resuming reference tests. The Linux 2014 subclass run continues independently under `continuation-subclasses-2014.log`.

Fresh native bookmark regression after event/attachment changes passed all three fixtures: `native-bookmarks-1793100757325317907/bookmarks.json`. The suite now freezes the executable and records its hash. Reader tree/action qualification remains pending.

## Original feature-menu and derived-attack qualification

`tools/native/fighting-styles` passed all three fixtures: `native-fighting-styles-1793101442990601077/fighting-styles.json`. It activates the original Class Features Menu widget and selects actual offered Archery/Dueling buttons, checks ranged hit and one-handed melee damage changes, saves/reopens and replaces the choice again. New scripted `button_path` resolves unique visible/enabled original controls and rejects disabled/ambiguous/missing choices. Source citations/check marks are optional in labels. 39 Rust tests and strict clippy pass. An earlier run failed because 2014 stores a leading plus in hit bonuses; assertions now compare the bonus numerically while retaining raw snapshots. Reader choice/mechanical qualification and all other class feature choices remain pending.

Post-resume qualification completed: `readiness-1793100140.json` passed all 24 cases with the frozen deployed harness and no new Reader crash/resource event. The controlled same-state print suite is now running (`continuation-reader-print-qualified.log`), first 2014 all-pages case passed; wait for terminal evidence before starting another Reader suite.

## Controlled Reader output qualification

Nine controlled Reader print cases passed: `native-printing-1793082799007399331/reader-print-output-1793101441773008623/print-output.json`, after 24/24 post-resume readiness `readiness-1793100140.json`. All/selected/generated companion ranges pass in all three fixtures, with no physical jobs. Native PDFs retain source media size; the Windows virtual printer used configured A4. OCR/render validation supplements outlined form-font text. This is operational printing evidence, not full appearance fidelity: subsequent inspection found material skill-label layout drift, currently under repair.

Independent Reader attachment metadata, FAQ menu and payload persistence passed all three original fixtures: `native-attachments-1793100475546677964/reader-attachments-1793103051862982338/reader-attachments.json`. Desktop launching, Reader file-export interaction and attachment import/modification remain unqualified or unsupported.
