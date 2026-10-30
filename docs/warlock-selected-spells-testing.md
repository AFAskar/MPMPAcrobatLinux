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
