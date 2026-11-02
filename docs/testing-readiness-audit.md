# Development environment readiness audit

The acceptance target is an automated Acrobat reference environment for developing the native Linux reader. Compatibility of the future Rust implementation remains a development target. Evidence below is from real Adobe Acrobat Reader 26.2.22031.0 on Windows 11, with protocol 3, 4 vCPUs and 4 GiB RAM.

| Requirement | Authoritative evidence |
|---|---|
| Real Reader, JavaScript and Linux development tools | Post-host-restart preflight: 27/27 checks, including pinned build, deployed helper/adapter hashes, trust, protected mode, clock, SSH/SCP, Rust/Cargo, Clang, CMake, pkg-config and Poppler. |
| Automated interactive desktop and file access | Local SSH port 2222; automatic Windows login; scheduled interactive worker; host lock and one desktop queue. Post-restart `up` succeeded unattended. |
| Both rulesets and representative characters | `readiness-1793002748.json`: 24/24 cases, 1715.552 seconds. Includes current 2014/2024 sheets, multiclass, manual add-ons, companion pages, wolf wild shapes and first-level Druid spell generation. |
| Supplied filled character | Ashnar read, original class-dialog cancellation, spell regeneration and saved-file roundtrip passed; decoded imported scripts and remembered spell state preserved. |
| Real file-import workflow | `file-import-1793002359.json`: 2/2 passed, 180.396 and 198.866 seconds. Uses the actual file picker, original import/execution functions, save/reopen, and independent complete payload comparison. |
| Saved PDF correctness | Linux verifies canonical field values, widgets, decoded appearance text, document-script hashes, and compressed imported-script values. Saved files reopen in a fresh Reader process. |
| Rendering | Poppler rendered 14 front/generated/spell-page images from the passed readiness outputs. Contact sheet and detailed spell/wild-shape pages visually reviewed; populated appearance values and generated content are present. |
| Original fixtures and source | SHA-256 manifest in fixtures.json; host originals checked by preflight; guest originals read-only. Read-only inventory: 25/27/25 document scripts and 3634/3627/4241 canonical fields for 2014/2024/Ashnar. |
| Repeated operation reliability | Corrected post-host-restart `stability-1793005974.json`: 6/6 passed, including three layouts per ruleset and Unicode input; final crash/resource audit passed. Functional cases took 1070.908 seconds combined. The earlier timestamp-bug report remains failed and preserved. |
| Clean restorable baseline | `restore-proof-current.json`: cold checkpoint `candidate-p3-4g-1793001620` restored, changed sentinel reverted exactly, recovery disk retained, automatic boot and 27-check preflight verified. Includes disk, NVRAM, TPM and domain XML. |
| Coding-agent handoff | AGENTS.md and testing-environment.md provide commands, preservation rules, menu context, asynchronous dialog handling, import continuation, bounded responses, source extraction, and cold-only recovery. |

Local evidence lives under `output/testing/` and is excluded from Git, including generated PDFs, screenshots, character data and logs. VM checkpoints are outside the repository. The JSON files named here are immutable run evidence; `readiness-latest.json` is a convenience copy.

Final machine-readable acceptance is recorded locally in `output/testing/qualification-final.json`, with evidence-file hashes and source fingerprints. The post-restart stability cases total 1070.908 seconds; these timings include input, calculation, save, process exit, reopen, download and independent verification.

## Failure history and current boundaries

Earlier Reader access violations occurred in EScript.api at 08:00 and 09:38 and AcroForm.api at 09:49 on October 26. Protocol 3 alone did not eliminate the EScript failure. The accepted core run uses full Reader process exit between documents and field focus after the response dialog returns. Its crash/resource audit passed. This is measured reliability over the defined runs, not a guarantee that Reader can never crash.

The first six-case stability run completed every functional case, but its final audit selected historical crash records because a per-case monotonic timer overwrote the suite wall-clock timestamp. That failed report is preserved. `stability-1793004464-corrected-resource-audit.json` checks the actual interval and has empty Reader-crash and resource-exhaustion lists. The fix retains separate suite and case timers.

After the 24-case readiness run, the stability timestamp fix changed `tools/acrobat/stability.py`, and a privacy cleanup removed the filled character’s sample values from `docs/fixtures.json`. Fixture filenames and hashes are unchanged. All adapter, control, readiness and PDF-verification source hashes still match the recorded fingerprint. The stability rerun qualifies the corrected audit independently.

Explicit-path `util.readFileIntoStream` fails on this Reader build; use the tested real file-picker continuation. Arbitrary URL imports, every third-party add-on, every dialog, and printing/export permutations are not covered. Oversized bridge results fail explicitly; use field summaries plus independently decoded saved PDFs for large payloads. The historical app-server/direct coordinate benchmarks in windows-reference-benchmark.md are not current oracle acceptance tests.

## Memory and restart

The VM was reduced from 6 GiB to 4 GiB; the 6 GiB cold checkpoint remains available. The 4 GiB smoke passed in 144.904 seconds with at least 6886.5 MiB host RAM available, versus 217.855 seconds and 5200.3 MiB in the preceding 6 GiB smoke. These separate runs are not a controlled speed comparison. Neither recorded a new Reader crash, guest resource exhaustion, or host OOM.

After the unrelated host logind restart, logind is active, the guest retained its 4 GiB configuration, and unattended startup passed all 27 checks. The restart did not erase the completed readiness, import, restore or corrected crash-audit evidence.

## Guarded virtual-printer and table probe extension

The application-menu adapter exposes print parameters, primitive field coercion,
and original resource/source/feature/rest/healing commands in disposable runs
only. The desktop helper's `save_print_output` is limited to an active original
MPMB print request, the native print-output picker, a new PDF in runs, and exact
native text write/readback before invoking Save. It does not choose printers.

Fresh preflight passed 27 checks and `readiness-1793078028.json` passed all 24
cases against the frozen deployed harness. `readiness-1793076904.json` remains
failed: its final integrity check detected a verifier edit during execution,
despite its 23 functional cases passing. Do not mutate fingerprinted harness
files while qualification is running.

Actual controlled virtual-print pilots saved files through this picker. Their
suites remain failed because text extraction / whole-page OCR missed outlined
form glyphs; visual inspection confirmed the printable sentinels. Retained
failures: `reader-print-output-1793079677723119752` and
`reader-print-output-1793082174845072879` under the respective native-printing
run folders. Successful picker execution alone is not a printing suite pass.

## Result-dialog acknowledgement qualification (2026-10-28)

Fresh `output/testing/readiness-1793160489.json` passed all 24 cases after 27-check preflight. `smoke-1793159933.json` passed keyboard/calculation/save/reopen in 139.173 seconds with at least 5415.2 MiB host memory available. The focused regression `reference-receipt-1793160305270823802/receipt-control.json` passed an oversized 128-field result receipt whose OK center lay outside its dialog, then verified PDF field focus with checked paste, independent saved canonical value and original script hashes.

The helper acknowledges result dialogs using the observed native button. A mouse click requires an exact WindowFromPoint handle match. An occluded/off-dialog button uses Space only when the exact foreground Reader result dialog and native OK keyboard focus are verified. The helper waits for closure and preserves Acrobat's own focus restoration. No fixed coordinates or blind keyboard macro is used.

Retained failed revisions: `readiness-1793122524.json` (posted acknowledgement did not close), `readiness-1793123713.json` (21 cases passed before refusing a taskbar-covered button center), and `readiness-1793158467.json` (forced native SetFocus disrupted PDF field focus). Each failed document was retained/closed before another suite. The final helper removes forced SetFocus; none of those failures is reclassified as a pass.

## Focused native OK acknowledgement qualification

`output/testing/readiness-1793163598.json` passed all 24 cases in 1203.701 seconds with fingerprinted inputs unchanged and no new Reader crash/resource-exhaustion event. Preflight `continuation-focused-space-preflight.log` passed 27 checks. The helper now prefers Space only when the exact result dialog's native OK owns focus, otherwise retaining its verified native-button pointer guard; it never forces SetFocus. The separate heavy-rendering/oversized-result/focus/save regression passes in `reference-receipt-1793163431517421177/receipt-control.json`. Prior failed suites and the separately recovered 45-second stress timeout remain failure evidence. This qualifies the reference control transport, not complete native MPMB compatibility.

The scoped live dialog-edit revision passes28 preflight checks (`continuation-dialog-input-preflight.json`) and24 readiness cases (`readiness-1793400684.json`,1109.162 seconds), with an unchanged harness fingerprint and no new Reader crash/resource exhaustion. Focused class-dialog typing/callback/cancel/save qualification passes in reader-dialog-input-1793400565051014102/input.json. The first numeric-control selector failure remains retained, including verified closure in reader-dialog-input-1793400350712372382/cleanup.json. New capabilities use bounded cross-process edit text reads and exact owned editable-control focus; numeric combo state is not full label/gesture qualification.


## Reference result delivery qualified after document-menu return

Queued receipt delivery now passes29-check preflight (continuation-deferred-receipt-preflight.json), rich-event/oversized receipt/focus regression1793480396712155931, and full readiness1793480531:24/24 with unchanged harness fingerprint and no new crash/resource exhaustion. Previously failing enabled-calculation15-case1793481788034461133 and60-case1793481967662227786 probes now pass actual execution, live carrier checksum/scripts and clean process closure.

Only receipt presentation is deferred on a retained0ms timer; original commands execute synchronously in the target document-menu context. Exact receipt/owner/foreground/closure checks remain; field focus occurs after alert dismissal. Node protocol test validates scheduling, single pending result, no duplicate delivery, actual error/overflow results and focus sequencing. BM_CLICK-first was not restored. The original acknowledgement failures and failed carrier experiments remain failures. This is transport qualification, not completion of any broad native milestone. Use readiness1793480531 for the new fingerprint.


Ampersand-safe adapter revision qualifies with29-check preflight continuation-ampersand-preflight.json, two real rich/plain checksum+saved-PDF transport controls1793513675541045398 and readiness1793513831 (24/24, fingerprint unchanged, no new Reader crash/resource exhaustion). Negative1793513159788503697 proves old direct alert reads doubled ampersands. Native MPMB compatibility is not established by transport readiness.


2026-11-02: initial current preflight continuation-nov02-up.log FAILED the pending Windows restart gate. Clean restart with no document open resolved it; continuation-nov02-up-after-restart.log PASSES29 checks. Fresh output/testing/readiness-1793598704.json PASSES24/24 with unchanged harness fingerprints and no new Reader crashes/resource exhaustion. The cloud Windows guest remains unqualified.
