# Implementation handoff

## Current continuation — 2026-10-28

The Codex goal remains ACTIVE and incomplete. Historical sections below retain prior runs; this section supersedes their live handles and incomplete inventory counts. No earlier default-choice sweep establishes complete class/table compatibility.

All 597 registered fixture/class/subclass pairs have bounded progression/native-reopen evidence across separate frozen runs: 245 each in 2014/Ashnar and 107 in 2024. The final Ashnar shadowed slice passes in `native-subclasses-1793158468877370067/subclasses.json` (four cases after 69 earlier passes in retained failed `native-subclasses-1793129497504843511`). Two valid Rune Scribe/Wizard multiclass profiles pass in `native-rune-scribe-1793161054749756266/rune-scribe.json`, including slots, dice, progression, removal/readdition and native persistence. Reader source-profile parity and comprehensive feature/spell/feat/table choices remain unqualified.

Escaped single-line diagnostic recovery `field-events-1793162025932570113/recovered-escaped.json` verifies saved ASCII JSON against Reader's UTF-16 code-unit count/checksum, preserves NBSP/U+2028/emoji sentinel, and equals the native trace. Original embedded scripts match and the document was closed. Its original suite remains FAILED on acknowledgement timeout. Earlier unescaped NBSP traces cannot settle character normalization because their carrier field could change Unicode. Multiline/richValue/defaultStyle/XML remain incomplete, including Ashnar Class Features/Extra.Notes differences.

The committed result acknowledgement revision passed `readiness-1793160489.json` (24/24). A follow-up preference for the already-focused native OK control is deployed but not qualified. Its heavy rendering regression `reference-receipt-1793163250177559684` exceeded the original 45-second command deadline; the exact original request subsequently returned true without repeating mutations. This is retained as failure/recovery, not an acknowledgement or compatibility pass. Its document was retained/closed (`reference-receipt-1793163250177559684/cleanup.json`). A longer bounded transport regression must finish before new readiness/Reader probes. Native indexed-rectangle correction has 50 unit tests/build/strict clippy passing; a disposable fixture probe is pending Reader qualification. No broad milestone is complete.

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

## Operational printing and skill-label appearance repair

All nine controlled Reader PDF-output cases passed in `native-printing-1793082799007399331/reader-print-output-1793101441773008623/print-output.json`. The untracked `verify-print-output.py` is the tested driver; it creates fresh native print references from the same saved generated-page state, freezes its executable, renders every Reader page and guards the virtual destination. Paper dimensions differ (source-sized native PDF versus configured A4 Windows driver), and form glyph extraction often requires OCR. Do not claim pixel/appearance equivalence or physical printing from this pass.

Inspection of those prints revealed skill labels drifting onto the wrong numerical rows. The appearance correction reuses source embedded TrueType fonts and preserves newline-span sizes/baseline metrics. `native-skill-layout-1793103451251022228/skill-layout.json` passes all fixtures against original Reader font bytes/baselines and checks the 2024 wolf's numeric AC Format result while retaining its formula. A further snapshot fix preserves raw signed numbers when no Format action runs; final three-fixture regression passes in `native-skill-layout-1793104464836966168/skill-layout.json`. The earlier numeric-only Format implementation exposed raw `10+Dex` in a small AC box; this is now rendered as `12`. Rich-text events, default styles, mixed-span fonts and non-BMP text remain incomplete.

Independent Reader attachment metadata/menu/payload persistence passed all three originals: `native-attachments-1793100475546677964/reader-attachments-1793103051862982338/reader-attachments.json`.

Independent Reader table suite `native-table-1793082877958892618/reader-table-1793101952982474278/reader-table.json` remains FAILED. Fighter resource/rest/healing phases matched, but the Monk ApplyClasses call paused at its explicit tool-proficiency ASK USER DIALOG. The known default was inspected and accepted, the original request completed, and the disposable was saved/closed as failure-retained. The driver needs explicit handling of this choice rather than broad auto-confirmation. Full Fighter comparison has seven differences: six serialized internal objects plus Class Features paragraph ordering; investigate line-ending/rich-text behavior.

Extended event probes measured Reader newline normalization: single-line fields convert CR/LF/CRLF to spaces before commit events; multiline Extra.Notes normalizes to CR. The expanded single-line run failed comparison as expected (`field-events-1793103318192533782`). The multiline run failed transport during its final read; its successfully executed data was recovered separately in `multiline-reader-recovered.json`, and its PDF was retained/closed. Keep that suite failed; obtain a fresh isolated pass after repairing semantics. Rich multiline assignments also deliver commit events for unchanged values and format once, unlike plain single-line numeric assignments.

## Newline and rich-mode commit correction

Implemented measured line endings before commit events, source RichText flags, rich unchanged-value validation/format cadence, empty rich-value clearing, and RichText/multiline flag persistence for text fields only (do not confuse those bits with button/choice flags). Isolated exact Reader traces pass: `field-events-1793105208509857092` (Player Name) and `field-events-1793104744998160239` (Extra.Notes). The real Class Features paragraph order now matches the independent 2014 Fighter output. Full `event.richValue`, default styles and rich XML persistence remain incomplete.

43 Rust tests and strict clippy pass. Native regressions: `native-table-1793104929774042202`, `native-generated-1793105209709603335`, `native-extended-1793105357416395385`, `native-lifecycle-1793105981695578429`.

Reader table rerun `native-table-1793104929774042202/reader-table-1793105389557601196` remains FAILED after three passing cases (2014 Fighter/Monk and 2024 Fighter): its guard rejected the observed default `Artisan's tool or Musical instrument` because of capitalization. Inspect/retain/close the pending 2024 Monk request before starting another suite. Accept only this verified Tools/Monk default profile; other tool choices are unqualified.

The frozen 2014 subclass sweep passed 143 regular cases and stopped at Sidekick Mage because generic alert response 1 did not affirm its explicit Yes=4 conversion warning. This was an incomplete test profile, not a proven engine failure. Diagnostic `sidekick-confirmed-report.json` in that run shows correct Mage level 3, base 2d8 becoming 4d8, and disabled race/background automation after confirming. Build a genuine sidekick profile with explicit HD controls (`ASK USER DIALOG` r000/r001), valid base creature inputs and all five sidekick variants. Legacy default alert codes also need stricter validation before broad reports can claim genuine user-choice coverage.

## Explicit sidekick and response validation

Runtime scripted alert replies now require buttons actually offered by nType; Yes/No uses 4/3, and generic 1 is invalid. Optional exact title/checkbox input is supported, and alert requests are captured alongside dialog traces. The dialog `header` guard checks the original static head control. 44 Rust tests and strict clippy pass.

`tools/native/sidekicks --fixture 2014` passed Expert, Warrior and all three Spellcaster roles in `native-sidekicks-1793106581875525010/sidekicks.json`: explicit conversion Yes, 2d8 base HD, Bandit base abilities, manual race/background, 3→1→5→11→17→20→3, HD total level+1, strict saved canonical fields, displayed d8+1 and native reopen. The first profile run failed the generic verifier's raw-die-versus-formatted-die expectation; the final test separately validates canonical 8 and visible d8+1. Base proficiencies/attacks, HP, all feature/spell choices and Reader remain unqualified. Other fixtures run under `continuation-sidekicks-other.log`.

The 2014 all-source inventory offers 172 subclasses, not just the 143 regular cases reached before the sidekick setup boundary. Twenty-six Artificer/ranger-variant/Mystic cases follow the sidekicks in definition order; `continuation-subclasses-2014-remaining.log` is exercising them with strict alert validation. New subclass-audit reports list candidates and unattempted candidates explicitly on failure; old reports omitted trailing unattempted rows. The 2024 all-source inventory offers 107 subclasses; 104 distinct regular cases passed across the earlier broad/Warlock-Wizard slices, leaving the three sidekick caster profiles requiring their special setup. These counts are default-feature progression only, not universal class/table qualification.

## Completed bounded table and sidekick qualifications

All six independent Reader resource/rest/healing cases passed in `native-table-1793104929774042202/reader-table-1793106341581663938/reader-table.json`. The final driver handles only verified Tools/Monk defaults (case-insensitive wording, raw choice recorded) and records rather than hides complete canonical differences. Current full comparison differences are 6,11,6,11,9,6 for 2014 Fighter/Monk, 2024 Fighter/Monk and Ashnar Fighter/Monk; inspect them before claiming whole-state equivalence. Both earlier suites remain failed (timeout at an unhandled prompt; capitalization guard rejection); their pending commands were completed and retained/closed before restarting.

All fifteen native sidekick identity/HD/manual-mode/progression/save/reopen profiles pass: five 2014 cases `native-sidekicks-1793106581875525010`, ten 2024/Ashnar cases `native-sidekicks-1793106845145753682`. Reader equivalence, base proficiencies/attacks, HP and every feature/spell choice remain unqualified.

Reader original fighting-style command/attack comparison now runs via the untracked `verify-fighting-styles-acrobat.py` (`continuation-reader-fighting-styles.log`); it uses original app-menu ClassFeatureOptions, not Reader popup UI qualification. Do not start another desktop suite until terminal evidence and cleanup. The 26-case remaining 2014 subclass run is live under `continuation-subclasses-2014-remaining.log`; the Ashnar regular subclass run is live under `continuation-subclasses-ashnar.log`. Ashnar explicitly filters out Sidekick Spellcaster because the dedicated profile covers its required setup; new reports record that exclusion.

### Live continuation handles

At this checkpoint the overall Codex goal remains ACTIVE and incomplete. The only untracked source is the Reader fighting-style verifier, currently being exercised. Do not restart live work merely because observation takes time.

- Reader fighting styles: exec session 34599, log `continuation-reader-fighting-styles.log`, report folder `native-fighting-styles-1793101442990601077/reader-fighting-styles-1793107387113180523`; 2014 case passed, remaining cases live. No second Reader suite until it terminates and cleans up.
- Remaining 2014 subclasses: exec session 10487, log `continuation-subclasses-2014-remaining.log`, run `native-subclasses-1793106869845133839`; 26 candidates, through Mystic at this observation.
- Ashnar regular subclasses: exec session 80355, log `continuation-subclasses-ashnar.log`, run `native-subclasses-1793107324207137425`; 169 candidates, dedicated sidekick profiles excluded explicitly. This broad run is early in its cases.

Next concrete discrepancies from complete independent table comparisons: 2014/2024 Monk has blank-versus-Off unchecked checkbox values for Medium Armor, Heavy Armor and AC Stealth Disadvantage; determine actual `checkThisBox`/`isBoxChecked` behavior with an original manual add-on probe before changing it. Ashnar Fighter also differs in Class Features, Extra.Notes, Dex ST Prof and Proficiency Weapon Other; inspect meaningful differences rather than dismissing them as serialization. Serialized internal fields still require semantic comparison. Full rich-text event/default-style/XML persistence, mixed-span fonts, non-BMP text, direct document import/export, wider feature/spell/feat/multiclass/table coverage and repeated persistence remain incomplete.

## Fighting-style Reader qualification completed

All three independent original-command style/attack/save cases passed in `native-fighting-styles-1793101442990601077/reader-fighting-styles-1793107387113180523/reader-fighting-styles.json`. The driver is `tools/native/verify-fighting-styles-acrobat.py`; it uses original fixtures, original ClassFeatureOptions through the application-menu bridge, exact phase comparisons, and independent saved-field/appearance/script checks. Native evidence covers the real original feature popup; Reader popup interaction remains unqualified. No broad milestone is complete.

The remaining 26 regular 2014 subclasses passed in `native-subclasses-1793106869845133839/subclasses.json`. Together with the earlier 143 regular cases and three specially configured sidekick caster cases, all 172 offered 2014 subclasses have bounded default-choice progression evidence across separate frozen runs. This is not exhaustive feature or Reader qualification. Ashnar regular progression continues under `continuation-subclasses-ashnar.log`.

## Checkbox logical-value correction

`checkbox-events-1793108602307717102/checkbox-events.json` passes all three fixtures: original add-on runtime trace and independently inspected saved canonical values. Native loading now gives absent/empty checkbox/radio values the logical `Off`, with blank setters normalized likewise. The source dictionary remains untouched when unchanged; Reader's numeric `isBoxChecked` result was already correct and remains unchanged. Both pre-fix probes remain failed. 46 Rust tests, strict clippy, six table cases `native-table-1793108615879243486` and six generated cases `native-generated-1793108776371287331` pass.

The expanded rich-text whitespace probe `field-events-1793108856296515048/events.json` FAILED during its pre-save readiness dispatch (`Native control not found: OK`); Reader traces were obtained and show NBSP→space in Ashnar Class Features, unlike native. Its own document still requires retention/cleanup before another Reader suite. The original save mutation had not started: failure occurred in ensure_document's read-only functions request. Inspect that request/result before recovery. A separate initially-checked clearing mode is prepared in checkbox-probe.py but not yet exercised. No other Reader suite should start until cleanup.

## Correction: selectable candidates versus predefined inventory

The earlier wording “172 offered 2014 subclasses” was too broad. The original all-source inventory in `native-subclasses-1793106869845133839/2014-inventory-report.json` contains 245 non-excluded class/subclass pairs (235 unique subclass keys) across 21 classes. Only 172 pairs parse unambiguously to the requested class/subclass in that profile. The other 73 are still unexercised: 58 shadowed subclass pairs plus 15 pairs under the shadowed ranger class. Alternate source selections are required. The 172 bounded passing cases across separate frozen runs do not cover that complete inventory, every source profile or every feature choice. The 2024 all-source inventory has 107 selectable pairs; bounded evidence exists for all 107 across separate runs, without Reader or full feature qualification.

## Initially checked checkbox clearing

The independent Ashnar probe `checkbox-events-1793109091284805362` failed with equal runtime traces but different canonical values for initially checked Dex ST Prof and Proficiency Weapon Other. Reader removes `/V` when clearing them; native had written `/Off`. The projection now removes the canonical checkbox value while retaining widget `/AS /Off`; radio/pushbutton handling is unchanged. Corrected native/Reader traces and saved canonical values pass in `checkbox-events-1793109261986589690/checkbox-events.json`. All six native table regressions pass in `native-table-1793109263194871050/table.json`; 46 Rust tests and strict clippy pass.

The earlier failed Ashnar whitespace probe was retained and closed (`field-events-1793108856296515048/cleanup.json`); no save had started during its failed pre-save dispatch. A cleanup attempt used an unsupported `ready` script operation; it was corrected to the actual `ensure_document` helper and completed. The failed original probe remains failed. Expanded plain/rich NBSP qualification now runs separately under `continuation-rich-nbsp-boundary.log`.

## Target-only source profiles for shadowed subclasses

The Ashnar regular sweep completed all 169 candidates successfully in `native-subclasses-1793107324207137425/subclasses.json`; its three sidekick caster roles have separate profile evidence. All remain default-choice native progression, not universal table use or Reader equivalence.

New `--isolate-shadowed` mode in subclass-audit uses original source-element BTLA, selects the actual source-cited target leaf path, invokes BTR1 and applies. It asserts exactly the intended class remains enabled, then selects the original class/subclass controls and checks exact keys, levels, save and native reopen. The first UA Ancestral Guardian pilot passes in `native-subclasses-1793121267996131353/subclasses.json`: 73 candidates discovered, one exercised due to explicit limit. Earlier helper pilots failed on inaccessible local metadata functions (`amendSource`, `isNewAcrobat`); no product runtime repair was needed. Citation labels are derived from original metadata and still must match an actual offered complete path. 47 Rust tests and strict clippy pass, including ambiguous duplicate leaf rejection and exact parent/leaf selection. A Ranger/Hunter isolation pilot runs under `continuation-shadowed-ranger-pilot.log`.

## NBSP and rich-text mode commits

Text `.value` converts NBSP to spaces before K/V/F in both plain and rich fields. RichText=false runs Format even unchanged; RichText=true runs K/V/F even unchanged. Native behavior and the recovered full Reader trace agree exactly in `field-events-1793122032591996993/recovered-and-cleaned.json`; its saved PC Name diagnostic equals that trace and original scripts match. The original suite remains FAILED on result-dialog cleanup. Earlier Ashnar transition trace was likewise recovered and cleaned in `field-events-1793121604081621935/recovered-and-cleaned.json`. No Reader documents remained before helper deployment. 49 Rust tests and strict clippy pass, as do six table cases `native-table-1793122033811218055` and six generated cases `native-generated-1793122283200422875`.

Canonical Ashnar Class Features/Extra.Notes differences remain. The new NBSP setter behavior alone does not solve the rich Format path: event.richValue/defaultStyle and rich XML loading/persistence are still incomplete. Source `formatRichText`/`correctRichTextLineSpacing` use those APIs. Do not hide these remaining differences as serialization.

Repeated real Reader result-dialog failures exposed asynchronous repeated BM_CLICK acknowledgements in the harness. Pending desktop.ps1 changes activate the exact result dialog, click OK once and verify it closes. They are deployed, preflight passed, and fresh 24-case readiness runs under `continuation-result-ack-readiness.log`. Freeze all fingerprinted tools/acrobat inputs until it terminates. No other Reader suite may run concurrently. The harness change is not yet committed/qualified. Native source/profile work can continue.

## Independent stored-state comparison

New `tools/native/compare-state` distinguishes equivalent MPMB source serialization from different canonical state. It follows the original CurrentSpells `##########` split and compares evaluated data, with exact function source and explicit unsupported-type/parse failures. Its current source hash is qualified in `state-verifier-1793122607117204869/verification.json`: different-text 2014 Fighter baseline passes, and missing Character Level, changed CurrentVars and malformed CurrentVars native copies all fail as required. Both original inputs remain hash-identical. This is not a function-behavior or visual-compatibility certificate. An Ashnar Fighter comparison against the independent Reader output still fails on Class Features and Extra.Notes; its serialized internal state is equal under this strict comparator.

## Reference result-dialog failure and source-profile boundary

The first result-acknowledgement revision FAILED readiness at `blank-2014-roundtrip`: `readiness-1793122524.json`. The visible app.alert result ignored the posted button message even after activation. Its exact payload/OK button/foreground owner were observed; one verified Enter acknowledgement closed it. The failed reopened document was retained and closed in `readiness-1793122524-cleanup.json`. No failure is reclassified as a pass.

A second pending desktop.ps1 revision now clicks the freshly observed native OK button only after exact foreground ownership and WindowFromPoint button-handle checks, then verifies closure. It uses no fixed coordinates or unverified keyboard macro. It is deployed (`continuation-result-click-bootstrap.log`); preflight runs under `continuation-result-click-preflight.log`. Do not use it as a qualified oracle until fresh 24-case readiness passes. The harness edit is still uncommitted.

The 73-pair shadowed 2014 sweep FAILED after 41 passing cases in `native-subclasses-1793121437422195259/subclasses.json`: base Ranger/Gloom Stalker enabled both ranger and rangerua. Diagnostic replay shows original MergeElement moves matching labels under both parents, regardless of which one was selected. This is source-profile behavior, not a native parser repair. `gloom-profile-diagnostic.json` records the actual keys. The corrected profile excludes conflicting parent sourcebooks through the original sourcebook list before selecting class elements. Gloom Stalker now passes in `native-subclasses-1793123485647904376/subclasses.json` with actual `UA:RR` book exclusion recorded. The tool changes are pending; a remaining-32 run (`continuation-shadowed-2014-remaining.log`, session 73416, folder `native-subclasses-1793123574153776825`) preserves the 41 prior passing cases' provenance and also checks book exclusions after native reopen. Do not restart it merely because observation takes time.

The Ranger book-exclusion profile is now committed with the audit helper. Four cases in the remaining-32 run had passed at commit time; the run remains live. Its first Gloom Stalker case also checks UA:RR exclusion after native reopen. The prior failed 73-pair run remains failed. New reports describe sourcebook exclusions explicitly and use `profile_mode=isolated-shadowed`; legacy target-only reports are accepted for provenance-preserving resume.


## Unicode-safe diagnostic transport

`tools/native/field-event-probe.py` now escapes all non-ASCII JSON before writing its carrier field, includes a literal NBSP/U+2028/emoji sentinel, and independently checks a saved Reader output against `field_summary` UTF-16 length/Adler checksum. `--rich-data` records span/default-style/event state; it is diagnostic coverage, not an implementation claim. Python compilation passes. The retained escaped single-line output was independently rechecked for ASCII, sentinel, checksum, complete native trace equality and source script hashes. Its original suite remains failed; no mutation was repeated during recovery. Native-only rich-data evidence `field-events-1793124578797184537/events.json` has passed=null, as required. The repository rule now requires this encoding proof for field-carried diagnostics.

## Indexed widget rectangle correction

Base-field rect assignment now changes only widget 0; indexed rect reads/changes the selected widget and returns a copy. Original formatRichText reads indexed rect, so this affects reachable MPMB layout behavior. Fifty Rust tests, build and strict clippy pass (`continuation-widget-rect-{unit,build,clippy}.log`). `widget-rect-1793163356548767738/rectangles.json` verifies two actual 2024 widgets, independent saved PDF geometry, script hashes and fresh native reopen. Native-only report has passed=null; Reader comparison remains pending reference qualification. The first probe failed because its retained manual add-on translated again on reopen; the corrected probe clears the one-shot add-on before saving. This translation-only case does not qualify resize/reflow, rotations or all indexed properties.
