# Native MPMB implementation milestones

The active Codex goal is complete reachable MPMB behavior in all three authorized PDFs. No milestone alone completes that goal. A milestone stays in progress until its stated evidence exists; unsupported cases and unexercised choices remain explicit gaps.

| Milestone | Required evidence | Status |
| --- | --- | --- |
| 1. Printing | Original page-selection dialog and print function; all/selected/generated pages; field visibility, duplex, cancellation; independent print artifact inspection/rendering; real Windows Reader controlled print workflow and reopened native output | Nine controlled Reader PDF outputs and three native fixture suites pass; CUPS/physical/advanced settings and broader appearance qualification remain incomplete |
| 2. Source, class and subclass selection | Original source-selection and class/subclass dialogs, inventory after source changes, every exposed definition with explicit exclusions/ambiguities, meaningful derived feature checks against Reader | In progress; existing 38 base-class cases cover only level/proficiency progression |
| 3. Real table workflows | Per-class progression/change/removal, feature/spell/feat choices, multiclass, attacks/armor/conditions, rests/resources, generated pages and imports; explicit assertions against Reader | Six native Fighter/Monk resource/rest/healing cases plus three original Fighter style-menu/attack/persistence cases pass; Reader comparisons and broad coverage remain incomplete |
| 4. Persistence and presentation | Native and Reader save/reopen of qualified table states; complete canonical field comparisons, widget flags/geometry, appearance and rendering checks, scripts and imported/remembered state | Partial earlier probes; known differences unresolved |

Concrete run reports remain under ignored output/testing. Current evidence and unresolved behavior are recorded in native-compatibility.json, mpmb-compatibility-audit.md and development-handoff.md. A failed suite remains failure evidence even when a later repaired run passes.
