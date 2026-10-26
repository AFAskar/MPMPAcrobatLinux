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
