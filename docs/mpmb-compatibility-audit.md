# MPMB compatibility audit — 2026-10-26

Current qualification update (2026-10-28): all 597 registered fixture/class/subclass pairs (245 each in 2014/Ashnar, 107 in 2024) now have bounded default-choice progression/native-reopen evidence across separate frozen runs and defined alternate source profiles. Historical counts below describe earlier runs. This does not qualify every feature choice, Reader source selection or complete table use. Two additional valid Rune Scribe/Wizard profiles cover shared slots, hit dice, removal/readdition and native persistence; spell/feature choices and Reader parity remain incomplete. See [development-handoff.md](development-handoff.md) and [implementation-milestones.md](implementation-milestones.md) for current evidence and remaining acceptance work.

ASCII-escaped diagnostic recovery establishes exact single-line native/Reader trace agreement with a Unicode sentinel and saved-field checksum. Earlier unescaped NBSP measurements are unproven because the carrier field could normalize Unicode. Multiline rich spans, defaultStyle/event.richValue/XML and the remaining Ashnar Class Features/Extra.Notes differences still need implementation and independent qualification. The original failed transport suites remain failed.


**The 100% MPMB compatibility goal is not achieved.** The target is the complete behavior needed by the three supplied paid PDFs and real table usage with any predefined class. General Acrobat JavaScript completeness is not the target. The first runnable milestone and selected generation workflows are working, but do not meet that broader goal.

Original 2024 notes formatting now emits four embedded Segoe UI faces, selecting fonts and measuring advances per rich span. The 87-test build matches the captured Reader APIs and face set in `rich-format-1793371498418903278/formatting.json`, with original actions and scripts preserved. The overall comparison remains **FAILED**: underline/strike paths are absent and the heading baseline differs (365.04453 native, 366.882 Reader). These results are progress within Milestone 4, not completion. Fractional sizes, short leading, glyph widths, mixed-family typography and fuller class/table persistence still require qualification.

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

## Text-field commit normalization

Reader measurements establish that plain single-line fields convert CR/LF/CRLF to spaces before commit events, while multiline fields use CR. Rich multiline fields also validate unchanged assignments and format once. The native host now mirrors those measured paths, reads the source RichText flag and persists text-field RichText/multiline changes. Exact isolated traces pass for Player Name and Extra.Notes: `field-events-1793105208509857092/events.json` and `field-events-1793104744998160239/events.json`. Full rich-text event/default-style support remains incomplete.

This corrects the actual Class Features paragraph-order mismatch in the independently generated 2014 Fighter comparison. Native resource/rest/healing (six), generated-page (six), lifecycle (two), and import/Ashnar regressions pass after the change; see the matrix for reports. Reader table qualification remains incomplete: three cases passed before a guarded 2024 Monk tool-default capitalization mismatch stopped the second reference run. Failed suites remain failed.

## Bounded fighting-style reference evidence

The six resource/rest/healing Reader cases subsequently passed in `native-table-1793104929774042202/reader-table-1793106341581663938/reader-table.json`; complete canonical differences remain recorded. Three independent Reader Archery/Dueling attack and save cases also pass in `native-fighting-styles-1793101442990601077/reader-fighting-styles-1793107387113180523/reader-fighting-styles.json`. These execute original feature commands, while the native suite exercises the original popup. Reader popup interaction and wider feature choices remain unqualified.

## Checkbox logical values and retained PDF state

Reader exposes unset checkbox values as `Off`, and returns numeric `0`/`1` from `isBoxChecked`. Native loading and blank assignments now match those measured behaviors while preserving absent source `/V` when the final value is unchanged. All three original-addon trace/canonical-save comparisons pass: `checkbox-events-1793108602307717102/checkbox-events.json`. All six native table cases and six generated-page cases pass after the change; 46 Rust tests and strict clippy pass.

Comparisons against the earlier independent Reader table outputs remove three checkbox differences from each current-edition Monk state (11→8 differences, all remaining fields serialized state). Ashnar still has initially checked fields saved as Off versus absent after class replacement, and NBSP differences in Class Features/Extra.Notes. Those are unresolved; do not classify every remaining difference as harmless serialization.

## Correction: selectable candidates versus predefined inventory

The earlier wording “172 offered 2014 subclasses” was too broad. The original all-source inventory in `native-subclasses-1793106869845133839/2014-inventory-report.json` contains 245 non-excluded class/subclass pairs (235 unique subclass keys) across 21 classes. Only 172 pairs parse unambiguously to the requested class/subclass in that profile. The other 73 are still unexercised: 58 shadowed subclass pairs plus 15 pairs under the shadowed ranger class. Alternate source selections are required. The 172 bounded passing cases across separate frozen runs do not cover that complete inventory, every source profile or every feature choice. The 2024 all-source inventory has 107 selectable pairs; bounded evidence exists for all 107 across separate runs, without Reader or full feature qualification.

## Initially checked checkbox clearing

The independent Ashnar probe `checkbox-events-1793109091284805362` failed with equal runtime traces but different canonical values for initially checked Dex ST Prof and Proficiency Weapon Other. Reader removes `/V` when clearing them; native had written `/Off`. The projection now removes the canonical checkbox value while retaining widget `/AS /Off`; radio/pushbutton handling is unchanged. Corrected native/Reader traces and saved canonical values pass in `checkbox-events-1793109261986589690/checkbox-events.json`. All six native table regressions pass in `native-table-1793109263194871050/table.json`; 46 Rust tests and strict clippy pass.

The earlier failed Ashnar whitespace probe was retained and closed (`field-events-1793108856296515048/cleanup.json`); no save had started during its failed pre-save dispatch. A cleanup attempt used an unsupported `ready` script operation; it was corrected to the actual `ensure_document` helper and completed. The failed original probe remains failed. Expanded plain/rich NBSP qualification now runs separately under `continuation-rich-nbsp-boundary.log`.

## Exact rich persistence verification

The independent read-only verifier now requires exact expected span properties in the native reopen, Reader capture and native reopen of the Reader-saved file. It also checks canonical values, visible appearances, original scripts, unchanged source rich bytes and Poppler renders. Six artifacts pass in `rich-persistence-verification-1793188626355955262/verification.json`. Three damaged native/report controls (canonical value, appearance and expected style) are rejected in `rich-exact-verifier-negative-1793188742612341600/verification.json`; reference outputs were unchanged. This strengthens the bounded Extra.Notes evidence, without qualifying broader styles or complete compatibility.

## Companion formatted AC after fresh reopen

The original 2024 wolf keeps canonical AC `10+Dex` while Format computes 12 at Dex 15 and 14 at Dex 18. Native previously left the saved appearance at 12 after a fresh-process reopen. A retained Format signature now invalidates the appearance independently of canonical value changes. `formatted-companion-ac-1793189920828452420/formatting.json` passes native create/save/fresh reopen/change/save/reopen and an independently authored Reader save/fresh reopen/change/save. Decoded appearances and inspected Poppler crops show 12 then 14 in both. The real older stale native output is corrected on reopen/save; original scripts stay unchanged.

The 70-test binary also passes both acceptance slices, six generated cases and six resource/rest/healing cases; build, strict clippy and formatting pass. `tools/native/formatted-companion-ac --readiness output/testing/readiness-1793188033.json --stale-native output/testing/formatted-companion-ac-1793179731024048894/reopened-after.pdf` reproduces this bounded proof. Default-style persistence remains a verified failure: `default-style-persistence-1793189135222122217` assigns size 9/right/blue in memory but reopens at 7/left/black. Broader milestones remain incomplete.

## Initial rich getter coverage across all three fixtures

`tools/native/rich-initial-probe --fixture <2014|2024|ashnar> --readiness output/testing/readiness-1793188033.json` now passes exact comparisons for every initially rich text field: 68 in 2014, 72 in 2024 and 58 in Ashnar, including five/five/seventeen populated fields. It compares value, rich/multiline/readonly flags, alignment, size, font, color, defaultStyle and every rich span property without normalization. Saved ASCII carriers, independent Reader checksums/sentinel and original scripts are checked after close; optional getter errors are caught locally and no original field actions are replaced. Reports are `rich-initial-1793190374159866193`, `rich-initial-1793190159838317318` and `rich-initial-1793190495229915722`. This widens initial API evidence; edited default styles, plain-field styling, all class workflows and full appearance fidelity remain incomplete.

## Reader-authored widget styles and source colors

The native loader previously forced black text colors and read parent /DA rather than widget-local overrides. Five original source controls expose measured 16-bit color rounding, ZapfDingbats alias resolution and the AL asterisk's ScalaSans widget override. The old 70-test binary fails this comparison (`default-style-roundtrip-1793191164521032233`); the repaired loader passes (`1793191123033627622`). It also normalizes Reader's /DS font-stretch:Normal keyword.

Independent Reader partial-defaultStyle and empty-defaultStyle runs (`1793190632227924814`, `1793191055887421696`) preserve state through fresh Reader reopen. Reader updates /DS and widget-zero /DA /Q while leaving parent /DA unchanged. Empty assignment yields defaultStyle size12 but field size0; existing spans retain prior styles. Four Reader-authored PDFs now load into native with every captured property exact (`1793191667549539036`, `1793191683765285347`). All report names use prefix default-style-roundtrip and styles.json. Reproduce using `tools/native/default-style-persistence --load-reference --reference output/testing/default-style-roundtrip-1793190632227924814/styles.json` and the empty-style counterpart.

The final loader binary passes 73 Rust tests, build, strict clippy, six table cases (`native-table-1793191699758910436`) and both acceptance slices (`native-acceptance-1793191845745641484`). Six generated cases pass on the preceding source-color/widget-font binary (`native-generated-1793191286141940113`), before the widget-alignment/keyword additions. Native partial defaultStyle assignment and style writing are still verified failures; this commit qualifies loading only. The first styled-input load failed on Normal/normal (`1793191535300158530`), and that failure remains retained.

## Bounded default-style editing and cross-reader persistence

Two Extra.Notes cases now pass exact native/Reader state comparisons: partial size9/right/blue and empty defaultStyle (`default-style-roundtrip-1793193174745423641`, `1793193323262196517`). The setter replaces omitted defaults rather than merging an old family. Empty style yields style size12 and field size0. Existing spans retain their old font/size/color/alignment. Changed /DS and widget0 DA/Q persist; parent DA bytes and other widgets are unchanged. DA uses ASCII content bytes; encoding it as UTF-16 caused real Reader InvalidGetError. Prototype `1793192687370262249` is retained as failure: original request269eb39803bc4c8c97a11a20d365d68d recovered, own document retained/closed, no mutation replayed. Diagnostic getters now catch errors locally.

Native save/fresh reopen matches independently authored Reader state, Reader then loads/saves native output, and native reopens that Reader save exactly. Canonical values, appearances, original scripts and renders pass. A homogeneous old rich font and paragraph alignment remain independent of changed defaults. The partial notes region matches Reader's native-output resave pixels exactly. Independent Reader-author output retains a measured 3-pixel baseline offset at144DPI (`appearance-observations.json`, `render-comparison.json` in the first passing folder); this is still incomplete.

The81-test binary passes build, strict clippy, both acceptance slices (`native-acceptance-1793193557323749203`), generated6 (`native-generated-1793193631913438539`), table6 (`native-table-1793193806356797742`), all three rich source/byte-preservation cases (`rich-metadata-1793193958780414755`) and exact52 rich runtime/7 style runtime comparisons (`default-style-writer-{rich,style}-runtime-comparison-179319{400,420}0000000000.json`). The seven-case comparison explicitly excludes rich payloads; the52-case comparison is exact.

Reproduce with `tools/native/default-style-persistence --readiness output/testing/readiness-1793188033.json --reference output/testing/default-style-roundtrip-1793190632227924814/styles.json`; use `--style-json '{}'` and reference1793191055887421696 for the empty case. Missing fonts fail explicitly. Wider vocabulary/color/font mappings, indexed styles, mixed-face/decorated rendering and full table persistence remain incomplete. No broad milestone is complete.

## Rich baseline and leading metrics

The original 3px notes shift came from using TrueType hhea bounds for first rich baselines. Reader uses widget-default PDF font bounds. Its later leading uses run-font typographic ascent/gap normalized through16-bit fixed point and truncated1000-unit values; negative typographic gaps are treated as positive. Explicit spacing still adjusts the next baseline when font size changes. No expected coordinates are written into PDFs or hardcoded into the renderer.

Thirty field cases now match exact API captures and baseline positions within0.002pt:18 isolated2024 cases (single line, two equal-size lines, changing7/9 sizes; spacing11/14/default), six2014 and sixAshnar cases. Native reports: rich-baseline-1793196494347971809,1793196507526957041,1793196518342756380,1793196763532406097,1793197644416810243. The six Reader reference reports and native binary hash are in the matrix. These diagnostics intentionally clear K/V/F actions; they are not original class-workflow passes. The first Ashnar attempt used an inactive background field and failed after save/close; the corrected profile uses active Flaw.

Five of six additional bundled-face cases match; rich-baseline-1793196529349915624 remains FAILED because RavennaJW renders with MyriadPro-Regular in Reader. Native renders RavennaJW. Source-reader reference verification independently recomputes saved carriers/checksums/scripts/appearance positions; six references pass and damaged baseline JSON is rejected (rich-baseline-reference-verification-1793198071485369310.json). Reader PDFs stay unchanged.

Current84 tests, build and strict clippy pass. Native acceptance2, generated6 and table6 pass in native-acceptance-1793197046088946415, native-generated-1793197117522942872 and native-table-1793197280950719017. Native output survives actual Reader save and native reopen in default-style-roundtrip-1793197701546258818.

`tools/native/field-render-compare <native.pdf> <reader.pdf> --field Extra.Notes` measures a45pt visible region at144DPI. The3px shift is gone, but strict equality still fails for66/54270 pixels (field-render-1793197183172485517). Equal-input positive control passes; different-text control rejects before rendering (field-render-1793197702641260424 and1793197707900571859). Mixed fonts/decorations, fallback/width differences and all-class presentation remain required work.

## Widget page and rectangle getters

The original2024 notes workflow revealed collapsed native page arrays and readable inactive-template rectangles. Reader returns[-1,2] for Extra.Notes, rejects its inactive widget0 rect getter with InvalidGetError, and exposes widget1 coordinates at16-bit fixed-point precision. Native now matches the entire captured API state exactly (widget-api-comparison-1793200400000000000.json). The old binary is rejected by the same saved-carrier/checksum/script/action verifier (widget-api-old-counterexample-1793200400000000000.json). Raw source geometry is preserved.

The86-test build passes strict clippy and both acceptance slices, generated6 and table6 (native-acceptance-1793201246778624999, native-generated-1793201318845422257, native-table-1793201486593913362). `verify-widget-api.py` explicitly checks APIs only. The enclosing rich-format workflow remains FAILED for rendering: Reader uses regular/bold/italic/bold-italic Segoe UI and underline/strike paths, while native still uses one face. Do not count the API result as presentation or whole-workflow completion.


Rich span metric normalization is now measured separately: Reader rounds textSize/linespacing to one decimal using ties-to-even on the underlying binary value (7.25→7.2,8.05→8.1,14.75→14.8). The88-test host matches all six API captures in rich-baseline-1793372412020922365, but that suite remains FAILED because two short-leading baselines differ. Original MPMB's computed heading8.049999999999999 now becomes8 as in Reader (rich-format-1793372544623347380); decorations and placement still fail there. Scalar/defaultStyle fractional properties and immediate event timing remain unqualified.


First-line layout now matches18 isolated field cases including fractional, inline mixed sizes and the leading threshold. Original notes APIs/first baselines also match all three fixtures;2014/2024 face sets match. Corrected2024 baseline366.88202 matches Reader366.882 and survives genuine Reader save/native reopen (`rich-font-roundtrip-1793372931228998769`). The89-test build passes both native acceptance slices. Overall original notes suites remain FAILED because decorations are absent; Ashnar additionally renders2 faces while Reader uses4. Its italic/bold-italic faces are absent from the original form font resources despite being installed through fontconfig. This is a concrete next font-lookup failure; do not extend the2014/2024 four-face claim to Ashnar.


Ashnar now matches all four Reader faces through exact installed TrueType lookup, preserving embedded-font priority and rejecting unrelated Fontconfig substitutes.90 tests/build/strict clippy and native acceptance2 pass. Original notes APIs/faces/baseline match in rich-format-1793373501083515876; real Reader/native roundtrip passes in rich-font-roundtrip-1793373589948832107. Poppler crops show the four faces; strict pixels still fail360/54270 including absent decorations. Untouched saved APs survive without system lookup, but a stronger edit/restore test fails (rich-font-roundtrip-1793373979018774601): Type0 appearance fonts are embedded yet not rediscovered for editing. Portable font reuse is still required; the milestone remains incomplete.
