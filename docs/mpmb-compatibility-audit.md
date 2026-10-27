# MPMB compatibility audit — 2026-10-26

**The 100% MPMB compatibility goal is not achieved.** The target is the complete behavior needed by the three supplied paid PDFs and real table usage with any predefined class. General Acrobat JavaScript completeness is not the target. The first runnable milestone and selected generation workflows are working, but do not meet that broader goal.

## Source-derived class checks

`tools/native/class-audit` obtains class definitions and source-selection parsing from each original PDF runtime in the native reader. Each tested class is applied through the document application context at levels 1, 3, 5, 11, 17 and 20, checking the selected class, character level and proficiency calculation. All 38 fixture/class cases pass, totaling 228 level checkpoints.

| Fixture | Class definitions | Native-parser cases tested | Excluded/ambiguous definitions not exercised | Listed subclass references |
| --- | ---: | ---: | ---: | ---: |
| 2014 | 21 | 13 | 8 | 235 |
| 2024 | 15 | 12 | 3 | 107 |
| Ashnar legacy fixture | 21 | 13 | 8 | 235 |

These are counts per fixture, not counts of distinct classes across versions. The native parser's selectable list has not been exhaustively compared with Reader's list after every source-selection configuration. Excluded/ambiguous definitions are coverage gaps, not proven incompatibilities. The listed subclasses have not been exhaustively exercised. The probe does not prove complete feature choices, spell choices, source changes, multiclass combinations, rests/resources, combat automation or per-class PDF roundtrips. Scripted default dialog replies do not establish every interactive choice path.

Local evidence: `output/testing/native-class-audit-1793046452594567379/classes.json`, with original-runtime inventory and per-case reports. Paid script bodies and private character values are not copied into this document or test source.

## Dropdown-driven subclass work

The first all-source 2024 run selected 35 subclasses through original dropdown handlers and passed its defined five progression/native persistence checkpoints before failing on Circle of Wildfire. It is an aggregate **failed suite**, and it spanned development builds. The Wildfire failure was an undefined companion hit-die value reaching original string formatting. A qualified Reader original-class run confirms empty hit-die fields and 20 HP at level 3. Host normalization fixes the targeted native regression; original document scripts are unchanged. A fresh full run now uses one frozen executable and hash. See native-compatibility.json for reports. Feature-choice defaults and all-source-only coverage remain limitations; no complete subclass milestone is claimed.

## Printing milestone in progress

The missing `getPrintParams`/`print` dependency failure has been implemented with synchronous live-state capture and actual flattened print output. `tools/native/printing` passes all three fixtures: twelve controlled print artifacts cover all/selected/generated companion pages, simplex/long-edge duplex, the original page-selection dialog, cancellation, and all four field display values. Independent PDF structure, extracted text and Poppler rendering checks pass; interactive saves retain original scripts and reopen natively. Evidence: `output/testing/native-printing-1793074562899703807/printing.json`.

This milestone remains **in progress** pending real Reader printed-file output comparison. Fresh 27-check preflight/24-case readiness, native destination-dialog cancellation, and real Reader print-dialog cancellation/save have passed for the defined fixtures; the latest evidence is in native-compatibility.json. Physical CUPS output is implemented but has not been submitted to a printer. Advanced Acrobat print settings are rejected explicitly. Earlier unsupported-print evidence remains under `output/testing/mpmb-scope-audit-1793046774015100548/scope.json`; it is historical, not a statement that the dependencies are still absent.

Original embedded source also uses unfinished attachment/export, document import/export and menu operations. Field styling/font/rich-text fidelity and some bookmark/dialog behavior remain partial. Earlier generated-output comparisons showed hidden-widget Print-flag differences. Per-widget flag preservation now passes fresh two-edition Reader roundtrips (see below); a 2024 `CurrentEvals.Stringified` representation difference remains; some Reader-regenerated appearance streams and rendered pixels differ. See [native-compatibility.json](native-compatibility.json).

## Additional validation

Fresh `up`, 27/27 preflight and 24/24 readiness checks passed. The 23 Rust tests, strict clippy, formatting, Python syntax and shell syntax checks pass. Fresh native milestone cases for both current sheets and native import/Ashnar persistence cases pass. Real Reader reopen/save passes for both lifecycle/action cases and all three native-saved fixtures. All 4,241 canonical values in the native Ashnar file match its Reader-saved counterpart, with original embedded scripts preserved. This complete value comparison is for that regression character, not all possible class configurations.

Evidence: `output/testing/readiness-1793046363.json`, `native-validation-1793047420184139528/validation.json` and its `ashnar-comparison.json`, plus the per-suite paths recorded in [development-handoff.md](development-handoff.md).

## Acceptance work remaining

1. Exercise every class exposed after supported source selections, including currently excluded/ambiguous definitions and valid prestige/sidekick level limits.
2. Cover each predefined subclass and its actual feature-choice dialogs, including spell selection, feats/ASIs, class resources and changes/removals during progression.
3. Compare meaningful class-specific derived fields and resource behavior against real Reader. Level/proficiency checks alone are insufficient.
4. Exercise short/long rests, HP/conditions, attacks/armor, spell slots/preparation, companion/wild-shape changes and imports in real table workflows, including valid multiclass combinations.
5. Save/reopen those states natively and in Reader; independently compare canonical values, widgets, appearances, scripts, generated pages and imported/remembered state. Resolve or explicitly qualify all material differences.
6. Complete the MPMB-used workflows that currently fail. Do not expand the requirement to unused Acrobat APIs, and never count a stub, ignored error, excluded case or default-only dialog probe as full compatibility.

This audit does not certify the viewer for unrestricted table use with arbitrary predefined class choices.

## Per-widget visibility correction

The native state now preserves each annotation's complete flags independently, including inactive template widgets. Indexed `getField(name + ".N").display` changes only that widget; base-field assignment changes every widget and preserves unrelated flags. Hidden assignment uses Reader's Hidden+Print bits. Template spawning retains the source widget's live flags.

Concrete evidence: `native-acceptance-1793081175283634562/acceptance.json` and real Reader reopen/save `native-acrobat-1793081649617013956.json`. Read-only comparisons `widget-final-native-2014.json` and `widget-final-native-2024.json` have **zero active-widget flag/geometry/state differences**. All canonical values match in 2014; 2024 retains one known serialized evaluator difference. This does not establish appearance/resource equivalence or all generated-state coverage. Older comparisons against native-seeded Reader outputs understated the original loss of unchanged Print bits; those damaged baselines cannot certify source fidelity.

## Printing and appearance qualification update

Nine controlled real Reader print artifacts passed: `native-printing-1793082799007399331/reader-print-output-1793101441773008623/print-output.json`, following 24/24 readiness `readiness-1793100140.json` after managed-save resume. No physical jobs were sent. Native outputs preserve source media dimensions; Microsoft Print to PDF used its configured A4 paper. Rendered/OCR checks cover all selected pages and visibility sentinels; most Windows form glyphs are outlined rather than extractable. These are operational printing checks, not proof of full appearance fidelity.

Visual inspection exposed wrong skill-label rows caused by substituted font widths and lost blank-line metrics. The correction reuses embedded TrueType faces when they cover the field text and preserves rich newline sizes. `native-skill-layout-1793103451251022228/skill-layout.json` checks 18 labels, source font bytes and baselines against preserved original Reader appearances for all three fixtures. It also catches numeric Format results (wolf AC raw formula `10+Dex`, visible `12`). The generic default appearance must preserve canonical signs such as `+4`; only an actual Format result may replace that representation. Mixed-span font/style support and rich-text event/default-style fidelity remain incomplete.
