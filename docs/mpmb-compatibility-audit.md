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

## Printing milestone in progress

The missing `getPrintParams`/`print` dependency failure has been implemented with synchronous live-state capture and actual flattened print output. `tools/native/printing` passes all three fixtures: twelve controlled print artifacts cover all/selected/generated companion pages, simplex/long-edge duplex, the original page-selection dialog, cancellation, and all four field display values. Independent PDF structure, extracted text and Poppler rendering checks pass; interactive saves retain original scripts and reopen natively. Evidence: `output/testing/native-printing-1793074562899703807/printing.json`.

This milestone remains **in progress** pending real Reader printed-file output comparison. Fresh 27-check preflight/24-case readiness, native destination-dialog cancellation, and real Reader print-dialog cancellation/save have passed for the defined fixtures; the latest evidence is in native-compatibility.json. Physical CUPS output is implemented but has not been submitted to a printer. Advanced Acrobat print settings are rejected explicitly. Earlier unsupported-print evidence remains under `output/testing/mpmb-scope-audit-1793046774015100548/scope.json`; it is historical, not a statement that the dependencies are still absent.

Original embedded source also uses unfinished attachment/export, document import/export and menu operations. Field styling/font/rich-text fidelity and some bookmark/dialog behavior remain partial. Full generated-output comparisons still show two hidden-widget Print-flag differences and a 2024 `CurrentEvals.Stringified` representation difference; some Reader-regenerated appearance streams and rendered pixels differ. See [native-compatibility.json](native-compatibility.json).

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
