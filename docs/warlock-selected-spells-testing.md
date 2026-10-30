# Selected Warlock spell workflow qualification

This is bounded Milestone 3 evidence for the original 2024 Fiend Warlock at level5. It does not establish complete Warlock or other class compatibility. The native tool selects actual original spell and invocation controls; it does not write selected-spell arrays or expected derived values into the runtime.

Run the existing all-source profile:

```bash
tools/native/warlock-spells.py
```

Retain the original startup source defaults for comparison with a fresh Reader fixture:

```bash
tools/native/warlock-spells.py --default-sources
```

Both profiles use three cantrips (Eldritch Blast, Mage Hand, Minor Illusion) and six spells (Hex, Armor of Agathys, Misty Step, Counterspell, Fly, Hunger of Hadar). Original menus add, remove and readd Agonizing Blast for Eldritch Blast, regenerating the spell sheet after each change. Assertions cover exact selected keys and invocation choices, +7 attack, damage changes from 2×1d10 to 2×1d10+4 and back, generated description effects, independent saved fields/appearances/script hashes and fresh native reopen. Reports record excluded source keys at every captured phase; equal class names alone do not prove source-profile equality.

The current92-test build passes the all-source case in `output/testing/native-warlock-spells-1793378309651107868/warlock-spells.json`. The default-source case passes in `output/testing/native-warlock-spells-1793401115160975684/warlock-spells.json`, retaining51 excluded sources at all four phases. These are distinct native runs, not independent Reader parity evidence.

Reader text-selection/generation and source-profile comparison are being prepared. Actual Reader invocation gestures, selected-state reopen and full state/rendering comparisons remain incomplete. Other spells/invocations, spell expenditure/rests, progression choices and comprehensive class/table workflows require additional qualification.

Both initial selection and final invocation states now have separate native PDF artifacts and fresh native reopen assertions. `selected_output`/`selected_reopen` report the pre-invocation snapshot, while `output`/`reopen` retain the final readded-invocation snapshot. This avoids comparing a Reader selection-only PDF with a native PDF that already includes invocation damage. The stronger runs pass under `native-warlock-spells-1793401396984359203/warlock-spells.json` (defaults) and `native-warlock-spells-1793401455339159012/warlock-spells.json` (all sources). The workflow continues using original feature menus after the intermediate save, so that save is also exercised during continued play. These runs do not establish Reader persistence or whole-state equality.

Fresh native reopen qualification now edits Quarterstaff and restores Eldritch Blast through the original field events before saving again. Both initial-selection and final-invocation states must produce a changed weapon damage value (observed1d6+4), then restore exact expected attacks, selected spell keys, invocation choices and generated description fields. Independently inspected edited snapshots are reported as `selected_edited_output` and `final_edited_output`; unchanged AP retention alone cannot pass. Both profiles pass: `native-warlock-spells-1793401659301222978/warlock-spells.json` (defaults) and `native-warlock-spells-1793401732760222531/warlock-spells.json` (all sources). Reader edited-state parity still requires its own workflow.

Read-only full default-source before/after edit comparisons pass for both native snapshots. Reports `warlock-selected-edit-render-1793402100000000000.json` and `warlock-invocation-edit-canonical-1793402100000000000.json` compare all4520 canonical /V values (declared string coercion and CR/CRLF→LF normalization),2402 widgets’ geometry/flags/states, original scripts and populated normal AP content (1001 initial,1002 invocation; all equal). Selected-state front-page Poppler72dpi pixels are identical and were visually inspected. These are native before/after comparisons; they do not establish Reader appearance equivalence, raw rich span equality or rendering equality for every page.

The actual Reader initial selection/generation case now passes in `reader-warlock-discovery-1793401830310415656/discovery.json`. Reproduce with the qualified readiness and matching native defaults report:

```bash
python3 tools/native/warlock-reader-discovery.py \
  --readiness output/testing/readiness-1793400684.json --select-spells \
  --native-report output/testing/native-warlock-spells-1793401659301222978/warlock-spells.json
```

The tool cancels initial option discovery, captures offered exact labels through an original script observer, reopens the saved sheet and types them into nine observed enabled native ComboBox Edit children under the actual Cantrips/Spells headings. Each entry requires exact ownership/focus, clipboard readback, Tab and live-text readback without an unexpected dialog. It uses the actual offered list/generation buttons. No selected arrays or derived expected values are written to Reader. The saved ASCII observer verifies Unicode sentinel and Reader code-unit/checksum7035/963743635. Linux independently verifies selected arrays, exact derived/generated fields and original scripts; Reader termination is checked. Six comparison checks pass: source exclusions as sets, cantrip/spell sets, invocation list, exact attack values and generated description with declared CR/CRLF→LF normalization. This covers initial spell selection/generation only. Reader invocation gestures, subsequent edited reopen, native Reader-output reopen, full state/appearance parity and other class/table choices remain incomplete.
