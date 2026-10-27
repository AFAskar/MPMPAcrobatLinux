# Acrobat reference environment

This repository uses Fedora for development and a local Windows 11 KVM VM running real Adobe Acrobat Reader as its compatibility reference. The reference executes the original MPMB JavaScript. No API key is required for the test harness.

## Start here

```bash
tools/acrobat/run up
tools/acrobat/run smoke
tools/acrobat/run readiness
tools/acrobat/run imports
tools/acrobat/run stability output/testing/readiness-latest.json
tools/acrobat/run render output/testing/readiness-latest.json
```

The dedicated Windows account is configured to log in automatically on boot, and guest sleep is disabled. Windows Update is configured to notify before download/install; update and refresh the baseline deliberately between test sessions. Keep the Windows desktop unlocked. Leave its keyboard and mouse idle during a suite. The interactive helper starts at Windows logon. If Windows is at the sign-in screen, log in as `mpmb-test` (no password). SSH is `127.0.0.1:2222`, identity `~/.ssh/mpmb_win_vm`; the private key stays on Fedora. Do not run the historical benchmark macros as reference tests.

`run` selects Python with pypdf, including the installed Codex runtime. For another machine, install `tools/acrobat/requirements.txt` and set `MPMB_PYTHON` to that environment's Python. SSH, SCP, libvirt, Poppler, Rust/Cargo, Clang, CMake and pkg-config are checked by preflight.

A libvirt managed save hibernates the guest to disk and releases its RAM. `tools/acrobat/run up` resumes the registered state; direct `virsh start mpmb-windows11` is the equivalent resume for the configured local libvirt connection. Existing TCP sessions may have ended, so reconnect and qualify the resumed reference with preflight/readiness. Preserve managed-save state during routine startup. Discarding it loses the in-memory session and is a recovery action, not a prerequisite for resuming. The reported managed-save continuation was resumed without discarding state; preflight passed 27 checks and `output/testing/readiness-1793100140.json` passed 24 cases.

## Fixtures and evidence

`docs/fixtures.json` records the original PDFs' SHA-256 hashes. The two blank sheets are v14.2.0+261023 (2014) and v24.2.0+261023 (2024). Ashnar is an existing level-12 Monk (Way of Shadow), v14.0.2-beta+251205, with imported content and a spell page. It is a separate legacy-version regression case. Preserve these originals.

Windows copies live in `C:\Users\mpmb-test\MPMB-Testing\fixtures` and are marked read-only. Each suite copies them to unique writable files under `runs`. Local generated material is under `output/testing`, excluded from Git. PDF text fields normalize line endings to CR; the manual add-on comparison normalizes only line endings while requiring the remaining content to match. The synthetic manual add-on is `Testing/addons/readiness-sentinel.js`.

`smoke` performs one real Reader keyboard/calculation/save/reopen roundtrip, independently checks the PDF, samples host memory every two seconds, and records Windows Reader crash and resource-exhaustion events. It refuses to start below 1 GiB of available host RAM. A failed smoke is a failure; inspect its unique JSON report and the linked desktop evidence before proceeding.

The current readiness definition has 24 cases: the original 21 workflows, first-level Druid spell generation through real dialogs for both current sheets, and a final check for new Reader crashes or Windows resource exhaustion. The earlier protocol-2 21-case result is historical evidence and does not satisfy this definition.

The suite inhibits host sleep for its duration. Each run writes a unique `readiness-<timestamp>.json`, including failures and elapsed times. A failure stops the suite; failed pilots remain available. Inner Reader command responses and outer desktop responses are separate logs, keyed by request ID. Desktop replies cross SSH as base64 of the exact UTF-8 response file, avoiding Windows console code-page conversion of Unicode captions. A successful dispatch does not establish that the requested PDF values are correct.

Saved outputs are checked independently with pypdf: canonical `/T` field values (independent of `/TM` export mapping names), page widgets, decoded appearance text for populated visible fields, and original embedded document-script hashes. Ashnar's imported-script payload and remembered spells are checked separately. Render outputs with Poppler and review the images as well. The harness reopens a byte-identical saved-file snapshot after obtaining exclusive read access and checking both SHA-256 hashes; this avoids an observed protected-mode broker failure on immediate same-path reopen.

Choice appearance checks compare canonical export values with the label from the PDF's `/Opt` array (for example stored `short rest`, displayed `SR`). Expected widgets on inactive named templates are enumerated separately from active page widgets; canonical values remain strict, and missing/unrepresented widgets still fail. `tools/native/verify-regressions.py <native-table-report>` verifies this using disposable native outputs and damaged negative copies; it never edits a fixture or reference output.

Do not edit any `tools/acrobat` Python, JavaScript or PowerShell source, fixture manifest, environment lock or readiness sentinel while a qualification run is active. The suite fingerprints these inputs and rejects the run if they change. Development under `src/` and `tools/native/` can continue independently.

## Coding-agent controls

```bash
tools/acrobat/run control health
tools/acrobat/run control inspect
tools/acrobat/run control ready runs/example.pdf
tools/acrobat/run control js read --params '{"path":"runs/example.pdf","fields":["PC Name","Str","Str Mod"]}'
tools/acrobat/run control js focus --params '{"path":"runs/example.pdf","field":"PC Name"}'
tools/acrobat/run control paste 'Exact text including final character'
tools/acrobat/run control js save --params '{"path":"runs/example.pdf","output":"runs/example-saved.pdf"}'
tools/acrobat/run control screenshot
tools/acrobat/run inventory
```

Use unique writable run copies. `readiness.py` demonstrates fixture preparation, multiclass creation, manual add-ons, companion templates, spell regeneration, and saved-file verification. `dialog_probe.py` demonstrates asynchronous class-dialog inspection and cancellation. For another modal workflow, submit `control js call --async`, inspect the real dialog, invoke its named controls, then retrieve `control result <request-id>`. The wrapper waits for initialization before asynchronous calls too. `invoke`, `keys` and `paste` affect the interactive desktop; `paste` requires exact clipboard read-back before committing with Tab.

Large imported-script fields can be stored as compressed PDF value streams. `canonical_fields` decodes their text; comparing a stream dictionary does not verify the payload. Use `control js field_summary` for bounded Reader length/checksum evidence, then verify the complete saved value on Linux. Oversized dialog responses fail explicitly and report whether the operation completed; never repeat a mutation merely because its response was too large.

For file imports, use the real file picker. The explicit-path `util.readFileIntoStream` route fails on this Reader build. `tools/acrobat/run imports` uploads a synthetic script, imports it through the picker, executes it, saves/reopens, and verifies that the existing bundled scripts and the new script are preserved. For a custom file already uploaded under runs:

```bash
tools/acrobat/run control js call --params '{"path":"runs/example.pdf","name":"ImportUserScriptFile","args":[],"file_picker":true,"import_file":"runs/addon.js"}' --async
tools/acrobat/run control select-file REQUEST_ID runs/addon.js
tools/acrobat/run control result REQUEST_ID
tools/acrobat/run control js call --params '{"path":"runs/example.pdf","name":"RunUserScript","args":[false,false]}'
```

The adapter exposes fixed operations and a whitelist of original sheet functions. Paths are confined to the test workspace; field changes and function calls require a disposable `runs` document, and saves require a `runs` output. Requests carry unique IDs, expiration and a Reader-session ID. Stale sessions are refreshed only after rejection before document execution. Mutation timeouts are not silently retried. Host commands serialize through a file lock and the desktop helper processes one queued job at a time. Completed queue files move into `processed`, preserving traces without rescanning the full history.

Routine dialog and response handling uses native Windows controls. Optional UI Automation inspection runs in a separate process with a 15-second deadline, so it cannot wedge the desktop worker. Fresh element bounds provide a fallback for controls without an invocation pattern. Keyboard input requires Acrobat to own the foreground. Focus acquisition refuses to click through another application covering Acrobat's title bar. Known startup handling accepts default source selection, closes MPMB's welcome message, and dismisses its informational changes reminder with its named Close button. File-access approvals are restricted to the test workspace; save approvals are restricted to `runs`. Unknown dialogs fail the operation and leave screenshots for inspection.

## Why the menu bridge matters

Protocol 3 invokes the trusted application-folder adapter from the target document's File menu. The interactive helper supplies the serialized JSON through an application request dialog and requires exact text read-back before submitting it. The original MPMB function and its follow-up timers execute in that document's menu context. Closing exits Reader cleanly after the JavaScript response has completed, verifies that all Reader processes have ended, and reopens saved files in a fresh process. The adapter checks that only one document is open before exit. The process-isolated protocol-3 implementation passed the 24-case acceptance suite on the restored 4 GiB baseline. The earlier per-command controller-PDF transport is retired. Historical EScript and AcroForm crashes remain recorded in the readiness audit. Calling a document function directly from the controller can leave calculations suspended. `ready` checks original initialization functions, application/document calculation flags and deferred-display state before use.

Reader uses the classic interface in this VM. First-run tips and commercial upsells are suppressed through Adobe's documented preferences. Protected Mode and Enhanced Security remain enabled; only the dedicated test directory is added as a privileged location. See Adobe's [menu API reference](https://opensource.adobe.com/dc-acrobat-sdk-docs/library/jsapiref/JS_API_AcroJS.html), [viewer preferences](https://www.adobe.com/devnet-docs/acrobatetk/tools/PrefRef/Windows/AVGeneral.html), [basic configuration](https://www.adobe.com/devnet-docs/acrobatetk/tools/AdminGuide/basicconfig.html), and [trusted locations](https://www.adobe.com/devnet-docs/acrobatetk/tools/PrefRef/Windows/TrustManager.html).

## Deployment and checkpoints

`tools/acrobat/run bootstrap` deploys the versioned Windows scripts, checks/uploads fixtures, and registers the interactive logon task. SSH invokes its installation script with execution-policy bypass for that process only. To exit Reader from its Home screen, use `tools/acrobat/run control keys '^q'` and verify that the Reader processes end; closing only the Home window can leave background processes. Document roundtrips use the adapter’s checked close operation. Restart Reader gracefully after updating the adapter; preflight checks the expected protocol, the Reader build pinned in environment-lock.json, and the deployed helper/adapter source hashes.

Checkpoints must include the system disk, NVRAM, TPM state and domain XML. The checkpoint tool refuses to operate on a running VM. Cleanly shut Windows down, then:

```bash
tools/acrobat/run vm create baseline-name
tools/acrobat/run vm list
tools/acrobat/run vm restore baseline-name
tools/acrobat/run up
```

Restore saves a recoverable pre-restore checkpoint first. Checkpoints are local under `~/VirtualMachines/mpmb-windows11/checkpoints`; keep them out of Git. Do not force-stop Windows to create a clean baseline.

The earlier app-server/direct timings remain in `docs/windows-reference-benchmark.md`. That benchmark describes the old coordinate macro and is not the readiness result for this harness. A Windows Codex app-server is an optional subscription-backed agent worker; normal regression tests use the direct host harness and consume no additional Windows model turns.

## Verified baseline and resource budget

The VM uses 4 vCPUs and 4 GiB RAM. The clean checkpoint `candidate-p3-4g-1793001620` has been restored and boot-tested: a deliberately changed sentinel reverted to its original SHA-256, and the changed pre-restore disk was retained in `before-restore-1793001990`. The previous 6 GiB checkpoint `candidate-p3-1793001060` is retained as a fallback. Checkpoint labels are local identifiers, not claims that a new checkpoint is needed for each run.

A restore returns the guest files to checkpoint time. Run `up`, `readiness`, `imports`, and `stability` afterward to regenerate and qualify new output files. In particular, stability consumes the guest run files created by the referenced readiness report; a local old JSON alone cannot recreate those files after a restore. Do not restore while Windows is running.

The 4 GiB smoke took 144.904 seconds and had a minimum of 6886.5 MiB host RAM available. The preceding 6 GiB smoke took 217.855 seconds with a minimum of 5200.3 MiB available. These are separate end-to-end runs, including startup and verification, not a controlled engine-speed comparison. The completed 4 GiB readiness suite took 1715.552 seconds. No host OOM or new Reader crash was recorded during that qualification interval. Keep suites serialized; extra coding agents do not improve desktop-test throughput.

The acceptance scope is the named workflows in `docs/testing-readiness-audit.md`. It establishes a usable reference for development, not exhaustive MPMB API coverage or compatibility of an as-yet-unimplemented Linux reader. Arbitrary URL imports, every add-on, every modal workflow, and all printing/export options require additional cases as development reaches them.

## Pinned upstream source

The public 2024 source checkout is a reference submodule pinned to `5d6e57c861643ca77764131bd5dc865389879667`. Run `git submodule update --init --recursive` after cloning, then inspect `git submodule status`. Keep it unchanged while comparing behavior with the qualified fixtures. Submodule initialization does not retrieve the local-only paid PDFs, filled character, evidence or VM state. Extracted 2014 document scripts continue to live under ignored `output/testing/inventory`, not in the source submodule.
