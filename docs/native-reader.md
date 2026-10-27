# Native reader development

This is an experimental native Rust application, not a claim of full Acrobat or MPMB compatibility. The Windows reference remains the oracle. Original paid PDFs and extracted scripts remain local and ignored.

## Build and run

Fedora prerequisites are Rust/Cargo, a C toolchain, X11 or Wayland, OpenGL/Mesa, zenity (file picker), Poppler, and DejaVu Sans. Use the pinned submodule; never update its revision implicitly.

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

The setup script downloads the pinned Linux x64 PDFium V8 distribution at chromium/8111 and checks its SHA-256. It retains the supplied third-party license bundle under ignored `output/deps`. PDFium's V8 runtime is deliberately unused. `MPMB_PDFIUM` overrides the shared-library location; `MPMB_FONT` overrides the Unicode appearance font (default Fedora DejaVu Sans path). `.cargo/config.toml` sets one build job and development debug symbols are disabled. Do not run large builds concurrently with suites.

The application takes a PDF pathname. Click a widget to select a field, toggle a checkbox, or run its original button action. Commit text edits through the field sidebar. The Class button and MPMB tools menu run original handlers. Save writes a new disposable file. Existing paths, including originals, cannot be overwritten. The compatibility diagnostics expose incomplete behavior. This UI is an initial development shell; source dialog layouts and rich text remain partial.

`tools/native/acceptance` runs both authorized fixtures, original startup, user field edits, dependent calculations, selection of first-level Fighter through the original class dialog handlers, rendering, save, native reopen, and independent pypdf/Poppler checks. Every run gets a unique ignored directory and per-operation JSON evidence. It checks fixture hashes and decoded original script hashes. A failure stops the run and remains a failure. Do not infer compatibility from a process exit alone.

Before native-to-Acrobat checks, qualify the reference as directed in AGENTS.md. Then use the Python interpreter selected by `tools/acrobat/run` to run `tools/native/verify-acrobat.py <native-2014.pdf> <native-2024.pdf>`. `--expected` accepts a JSON object of additional canonical fields to compare. The script uploads unique disposable copies, uses the serialized application-menu bridge, reads fields, saves through real Reader, and independently checks the downloaded file. It never writes oracle values with a PDF library.

The diagnostic CLI is:

```text
mpmb-reader sheet.pdf --probe scenario.json report.json
mpmb-reader sheet.pdf --desktop-smoke output/testing/unique-desktop-directory
```

Scenarios specify explicit `dialogs` responses, numeric `alerts`, and `steps` (`advance`, `edit`, `eval`, `assert`, `render`, `save`). Unanswered prompts and unsupported APIs fail explicitly. `eval` is a development diagnostic operating on the same document global as original scripts; application controls use the registered original menu commands. Desktop smoke creates a real native reader window and a real class dialog window, captures each framebuffer, and cancels the dialog. Scripted dialog tests exercise original handlers; they alone do not establish native visual correctness. Generated artifacts and screenshots must stay under `output/testing`.

## Architecture decisions

PDFium was evaluated first against its actual source and public C interface. Its `CJS_App::execDialog` returns success without implementing a dialog. Public PDFium embedding APIs do not expose replacement of the Acrobat JavaScript object model. Using that runtime plus a second form-state mirror would make missing behavior difficult to control. Reference: https://pdfium.googlesource.com/pdfium/+/refs/heads/main/fxjs/cjs_app.cpp

The current division is:

- `pdf.rs`: lopdf reads canonical `/T` hierarchies, widget geometry, inherited field attributes, additional actions, `/CO`, metadata, bookmarks, and embedded document scripts. It preserves the source object graph and decoded original scripts. A save projects the live state into a cloned graph and writes new values and real appearance streams. It persists changed additional actions without replacing unrelated shared action dictionaries. It does not write to the source document.
- `acrobat.js`: the one live form state, document globals, events, calculations, timers, menu registry, dialog execution, and serialization. Original embedded scripts execute unmodified and in PDF name-tree order. Numeric field getters follow Acrobat coercion while `valueAsString` preserves the string. Validations can reject assignments; calculation events follow the original active `/CO` ordering, and assigning `event.target.value` retains the result. Template-only calculation entries are inactive until spawning. Generated field definitions and calculation entries enter this same state.
- `runtime.rs`: bounded-memory QuickJS-NG via rquickjs, synchronous native callbacks, and explicit error reporting. The initial quick-js binding was replaced after a stack-limit failure; rquickjs exposes memory and stack limits. No original MPMB source is vendored into the executable.
- `render.rs`: PDFium renders a disposable projection. It flattens and reloads only the temporary render page so widget appearances are included without instantiating a second interactive form/JavaScript runtime. Saved PDFs retain interactive widgets and scripts.
- `ui.rs`: eframe/egui Linux windows. A separate native dialog process preserves synchronous `execDialog` call stacks; each control event returns to the original dialog handler. The application registry retains original toolbar commands. Pending timers execute chronologically in the document global context.

The Rust PDF graph is an input/serialization structure, not an independently editable form model. UI edits, script assignments, assertions, and saved values all use the JavaScript field objects. Structural page operations replay an explicit journal from that same state. Named templates clone page/field/widget ownership and resources; shared templates retain one logical field value. The saved calculation order comes from the live state. Do not add a second form manager to PDFium.

## Current boundaries

`docs/native-compatibility.json` records source call-site counts and explicit support levels. A partial implementation is never a compatibility pass. The eight original inventory categories do not cover every Acrobat API; extend the inventory with observed calls and focused behavior tests.

Focused Rust regression tests cover the implemented host paths; current counts and concrete runs are recorded in the compatibility matrix. Both editions have passed original companion (wolf), wild-shape (wolf), and Druid spell-generation workflows, native save/reopen, independent checks, and all six real Reader roundtrips. Named and shared template cloning, deletion, popup menus and native toolbar commands are implemented with limited coverage. Some MPMB import/export paths, bookmark destination details, complete field styling and dialog controls/layouts remain work. Template overlay is also unsupported, but the inspected MPMB calls request overlay=false; unrelated Acrobat APIs are not the acceptance target. Normal button icons use original PDF resources; matching normal/rollover/pressed captions persist. Distinct rollover/pressed captions and non-normal icon faces fail explicitly. New appearances reuse an original embedded TrueType face when it covers the text, with a Unicode BMP fallback. Full rich-text event/style/XML and mixed-span font fidelity remain incomplete. Non-BMP appearance text fails explicitly. Existing script streams and untouched appearances are retained. Adobe usage-rights signatures may be invalidated by full-file serialization; the tested Reader roundtrip, not a signature claim, is the acceptance evidence.

Do not ship this as a general untrusted-PDF scripting sandbox: resource limits are present but filesystem permission isolation and script trust controls are not yet implemented. Development use here is the user's explicitly authorized local fixtures and add-ons.

## Wider comparisons and diagnostics

`tools/native/compare.py <native.pdf> <reader-saved.pdf> output/testing/<unique-report>.json` compares every canonical field value, page count, widget count/geometry/flags/state, appearance presence, and decoded original document-script hashes. Its output records differences rather than equating the focused milestone assertions with complete compatibility. Reader can regenerate appearance streams and rewrite serialized internal objects; inspect those differences explicitly.

`MPMB_TRACE_FIELDS='Character Level' tools/native/run <sheet.pdf> --probe <scenario.json> <report.json>` records selected initial PDF values and script assignment stacks to stderr for debugging. Redirect private traces under `output/testing`; never commit them. Original caught exceptions and error dialogs are recorded in diagnostics and fail initialization. The runtime's revision counter refreshes rendered projections after timer-driven field changes.

The local extended suite derives the supplied character's expected values from its original PDF at run time, preserving privacy in tracked test code. It checks complete imported payload and remembered spell-field retention, not just a few visible fields. Generated workflow tests live in `tools/native/generated`; page hide/reveal/removal tests live in `tools/native/lifecycle`. Runtime errors and unmet independent assertions fail these suites.

## Qualified runtime repair

The user authorized a logged runtime repair for the original 2024 wild-shape typo: `ApplyWildshape` declares `prop` but reads `pop`. It is enabled only for the exact decoded Functions2 SHA-256 `ce4624265af7fad2456badd108fa6003e5dbb939263ee7269a4cbbf9e3055857` plus function-source guards. The runtime replaces those property reads in the loaded function; the original embedded PDF script bytes remain unchanged. Diagnostics and the native UI identify repair `mpmb-2024-261023-wildshape-pop-typo`. This is repaired behavior, not strict original-script compatibility.

Use `MPMB_STRICT_ORIGINAL_SCRIPTS=1` or append `--strict-original-scripts` to keep strict execution. The original failure is retained as failed local evidence. No other source is automatically patched.

`tools/native/verify-generated-acrobat.py <generated.json>` reopens each generated output, reads its expected canonical fields through the original application-menu bridge, saves with Reader, and independently checks the downloaded file. It serializes all operations. `tools/native/compare.py` reports wider differences, including internal representation and widget flags; focused passes do not imply byte-identical appearance streams.

## Compatibility target and audit

The target is all reachable MPMB behavior in the three authorized supplied PDFs, including every predefined class choice and real table usage. It is not full general Acrobat JavaScript. That MPMB target is not yet achieved. The original `PrintTheSheet` and `PrintButton` now produce controlled native print output for all three fixtures. The broader printing milestone still needs Reader and desktop qualification. Selected workflow passes must not be presented as full MPMB compatibility.

`tools/native/class-audit` discovers classes from each original runtime, tests currently selectable base-class progression at levels 1, 3, 5, 11, 17 and 20, and records excluded/ambiguous classes. It checks original class parsing, class level and proficiency calculations. It does not establish complete subclass, source-selection, feature-choice, spell-selection, multiclass, rest/resource, combat, appearance or persistence coverage for every class.

`tools/native/printing` replaces the historical negative printing probe with controlled output validation; it never sends physical jobs. Probe scenarios must set `print_output_dir` explicitly. The native destination dialog offers a new flattened PDF or an explicitly confirmed CUPS destination. Print copies contain only selected flattened pages; interactive saves preserve the document scripts and fields. Unsupported advanced print settings fail explicitly. See [implementation-milestones.md](implementation-milestones.md) for the staged acceptance work.

Repository and reference access have been restored. The former read-only-session failure remains retained evidence, and subsequent runs use unique evidence directories. See [development-handoff.md](development-handoff.md) and [native-compatibility.json](native-compatibility.json) for current results.

`tools/native/subclass-audit` exercises original source-selection buttons and class/subclass dropdown events, progresses selected subclasses through levels 3, 5, 11, 20 and back to 3, then independently checks saved outputs and native reopen. `--fixture`, `--class-key` and `--limit` constrain a diagnostic run and record unexercised cases. The current source profile includes all books/class elements; classes shadowed under that profile remain coverage gaps. Scripted `select` replies must name exactly one option offered by the original dialog; absent, ambiguous and disabled options fail. Feature dialogs currently use default replies and do not qualify all feature choices or table usage. Reader comparisons remain separate work.

`tools/native/bookmarks` exercises original bookmark handlers, creation/removal and action context on all three fixtures, independently checks outline links/style/color/open counts, and saves/reopens and executes the retained actions natively. The sidebar displays the live bookmark tree and executes actions with the Bookmark/Mouse Up target. Native focus and page-number changes update the displayed page. `python3 tools/native/bookmarks-desktop.py` captures the actual panel and navigation rendering on both current sheets. Reader qualification remains pending. Direct page destinations flag incomplete zoom/position handling; unresolved/named and other unsupported native action types fail explicitly.

`tools/native/table-workflows` tests original limited-feature use, short/long rest recovery and healing/hit-dice recovery for Fighter/Champion and Monk/Shadow at level 5 in all three fixtures, including native save/reopen. These six cases do not qualify other classes or all table workflows. Independent PDF checks include choice labels and inactive named-template widgets. `tools/native/verify-regressions.py` checks that missing widgets, missing choice appearances and damaged stored values still fail. Paired Reader verification must independently create inputs from the original fixtures; calculated native state must not be written into reference outputs.

### Embedded files

`tools/native/attachments` exercises the original FAQ menu/export and installation-helper dialog in all three fixtures, verifies exported bytes with independent pypdf extraction, renders the FAQ, and checks attachment/script/field-inventory retention plus native reopen. Probe scenarios require `attachment_output_dir`; requested launches are suppressed and recorded. Desktop exports use a native destination chooser; PDF launch mode uses a temporary file and the desktop PDF opener, removed when the runtime is destroyed. Existing destinations are never overwritten. Non-PDF launching and attachment import/modification remain unsupported.

`tools/native/verify-attachments-acrobat.py NATIVE_REPORT --readiness READINESS_REPORT` measures metadata/menu/persistence in independently opened Reader fixtures through MPMB's original manual add-on workflow. It does not validate Reader attachment-file export or native desktop launching.

`tools/native/fighting-styles` selects actual offered buttons in the original class-feature popup, asserts Archery/Dueling attack effects in all three fixtures, saves/reopens and changes styles again. Scripted `button_path` responses resolve unique visible/enabled controls under their displayed parent menu labels. Source citations and selection marks can be omitted; ambiguous/unavailable buttons fail. This is defined native menu/mechanical coverage, not universal feature-choice or Reader qualification.

Appearance projection reuses an embedded TrueType face when the requested field font covers its text, with `MPMB_FONT` as the Unicode fallback. Blank rich lines retain their own font-size metrics. `tools/native/skill-layout` compares all 18 skill labels and baselines against original Reader appearances, checks font payload identity, renders the generated companion, and verifies numeric Format results without changing canonical formulas. Mixed font/style spans, rich-text event/default-style behavior and non-BMP output remain incomplete.

`tools/native/sidekicks` exercises the special sidekick setup rather than bypassing its prerequisites: all-source selection, original class dropdowns, explicit conversion confirmation, base hit-dice input, manual race/background mode, level progression and native persistence. This is identity/HD/manual-mode coverage; base proficiencies/attacks, HP and all feature/spell choices remain unqualified. Probe `alerts` accept numeric button codes or `{"title":"Exact prompt","button":4,"checked":false}` objects. Invalid button codes fail; `MPMB_DIALOG_TRACE_DIR` also records alert requests. A dialog reply may guard its static `head` text with `header`.

`tools/native/verify-table-acrobat.py NATIVE_REPORT --readiness READINESS_REPORT` independently creates the defined Fighter/Monk inputs in original Reader fixture copies and compares baseline/resource use/short rest/long rest/healing phases. It explicitly handles only the observed Monk Tools prompt with its unchanged original default, saves/closes each document, then checks fields/widgets/scripts and records complete canonical differences. Passing phase checks do not certify all saved values or tool choices.

Scripted list selections accept an exact label or a full hierarchical label path, for example `"select":{"ExcL":["Revised Ranger","Hunter"]}`. Paths reject missing or ambiguous choices and preserve original list item identities. `tools/native/subclass-audit --fixture 2014 --isolate-shadowed` uses the original sourcebook and class-element dialogs to include only each targeted shadowed class/subclass; it checks the applied exclusion state and exact selected keys. This is bounded native progression evidence, not Reader or comprehensive feature qualification.

`tools/native/compare-state <native.pdf> <reader.pdf> <report.json>` compares canonical values while interpreting changed MPMB `.Stringified` expressions in a bounded Node.js context. It uses the original CurrentSpells/CurrentCasters separator, preserves array order and primitive values, and requires exact function source. Parse errors, unsupported types and nonserialized field differences fail explicitly. This is stored-state evidence; function behavior and widget/appearance/render fidelity require separate checks. `verify-state-comparison.py` qualifies it with an independent Reader baseline and damaged disposable native copies; reference PDFs are never edited.
