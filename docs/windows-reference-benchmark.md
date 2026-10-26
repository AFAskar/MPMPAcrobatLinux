# Windows Acrobat automation benchmark

> Historical benchmark of the original coordinate macro. The replacement harness is documented in `docs/testing-environment.md`. Field counts in this report are pypdf export-mapping entries, including parent entries; the new verifier follows terminal `/T` field names. Original timings and failures are retained.

Date: 2026-10-25 (UTC+3). Project: Linux Native MPMB Reader.

## Result

Direct control was 8.65 seconds faster per trial on average. Neither current helper configuration is ready for unattended compatibility testing. Every script completed, but independent PDF validation found exact-task failures that the helper's success flag and Windows agent's summaries did not detect.

| Route | Trials | Mean seconds | Range seconds | Exact passes | Stored field checks |
|---|---:|---:|---|---:|---:|
| Fedora direct SSH -> interactive Windows helper | 3 | 21.987 | 21.860-22.210 | 2/3 | 8/9 |
| Fedora -> Windows Codex app-server -> same helper | 3 | 30.640 | 30.009-31.294 | 0/3 | 4/9 |

The agent route took 1.394 times the direct time. This is a three-trial orchestration comparison using a shared scripted GUI helper, not evidence of an inherent model reliability difference or a benchmark of autonomous visual navigation.

## What was actually tested

The actual 2024 MPMB PDF (v24.2.0+261023) ran in Adobe Acrobat Reader 26.2.22031.0. Each trial opened an independent copy of the same initialized baseline, entered a unique character name and Strength score, saved a separate output PDF through Acrobat's GUI, reopened that output, and captured before/save/reopen screenshots. Scores were 18, 14 and 20, with expected modifiers +4, +2 and +5.

All field edits used desktop mouse/keyboard input. No PDF library wrote the expected values. Fedora independently read the saved AcroForm field values, checked their page widgets and appearance streams, and rendered each output with Poppler. Each output retained 6 pages and 4,165 named fields.

Environment: Fedora 44 / KDE / Wayland host; KVM guest with 4 vCPUs and about 6 GiB RAM; Windows build 10.0.26200.0; 1280x800 desktop; portable Codex CLI 0.146.0. Windows model/list offered gpt-5.6-sol as its default; the worker used that model at low reasoning effort.

Both original sheets are copied into the VM at C:\Users\mpmb-test\MPMB-Bench\source-2024.pdf and source-2014.pdf. Only the 2024 sheet was benchmarked.

## Per-trial measurements

| Trial | Route wall seconds | Desktop helper seconds | Stored character name | Stored Str / modifier | Value checks | Exact result | Extra worker tokens |
|---|---:|---:|---|---|---:|---|---:|
| direct-v4-1 | 21.860 | 19.831 | MPMB-RUN-D1-4827 | 18 / 4 | 3/3 | PASS | 0 |
| agent-v4-1 | 30.616 | 19.806 | MPMB-RUN-A1-482 | 18 / 4 | 2/3 | FAIL | 39,440 |
| direct-v4-2 | 22.210 | 19.885 | MPMB-RUN-D2-482 | 14 / 2 | 2/3 | FAIL | 0 |
| agent-v4-2 | 31.294 | 19.491 | MPMB-RUN-A2-482 | 14 / 2 | 2/3 | FAIL | 39,489 |
| direct-v4-3 | 21.892 | 19.709 | MPMB-RUN-D3-4827 | 20 / 5 | 3/3 | PASS | 0 |
| agent-v4-3 | 30.009 | 19.153 | MPMB-CALIBRATION | 16 / 3 | 0/3 | FAIL | 39,462 |

The required names ended in `4827`. Direct trial 2 and agent trials 1 and 2 stored `482`, losing the final digit. Agent trial 3 saved the baseline name and 16/+3 instead of the requested name and 20/+5; its pre-edit screenshot shows the view had remained in the pane layout, so the fixed coordinates missed the fields. These are failures even though the scripts returned success.

Five of six outputs stored the requested Strength and calculated modifier. Two of six outputs stored the exact requested name. Overall, 12 of 18 expected field values matched. The saved PDF appearance streams agree with the independently extracted stored values. No measured failures were silently retried or excluded.

## Timing boundaries and limitations

Route timing starts immediately before submitting the direct SSH command or agent turn and ends when the command/turn returns. Agent initialization, authentication and thread creation are excluded; direct SSH connection startup is included. Artifact downloads and independent validation are excluded from both timings. App-server initialization was separately observed at 0.964 seconds in an earlier startup probe (one sample).

Both routes executed the same 46-step GUI plan. It contains 14.90 seconds of explicit stabilization waits. These times are not minimum achievable latency. Runs were sequential and interleaved direct/agent for each score. A second agent invoked the plan and reported its returned metadata; it was instructed not to inspect screenshots during the timed turn. Therefore this tests delegation overhead and the current helper's behavior, not a vision agent's ability to recover from dialogs or changed layouts.

There is no basis for attributing the character truncation specifically to app-server: the same issue occurred through direct control. The common helper needs input completion/read-back verification. Layout changes require state-aware targeting instead of assuming a shortcut always selected the desired view.

## Subscription usage

The initial preflight reported ordinary usage allowed, with 57% remaining in the five-hour window and 90% remaining in the weekly window. At the later Acrobat-ready resumption, 44% and 88% remained. After all six measured trials, the last check showed 16% and 83% remaining. No reset was used; both reset credits remained available.

Those are shared account snapshots including setup, this parent conversation, probes, pilot attempts and potentially other account activity. They cannot be used to assign a quota cost to individual benchmark trials.

The three measured Windows agent turns reported 118,391 processed tokens: 117,561 input, including 111,744 cached input, plus 830 output. Reasoning tokens (25) are a subset of output. The direct route invoked no additional Windows model turn; the Fedora parent agent still consumes subscription usage.

App-server authenticated through ChatGPT external-token mode over SSH. No API key or paid API path was used. The Windows benchmark CODEX_HOME did not contain auth.json after testing; the refresh token was not copied into the guest.

## Pilot failures and scope

Earlier setup attempts are preserved separately from the v4 measured batch: direct-1, direct-v2-1 and direct-v3-1 exposed viewport and Save As assumptions. Agent-1 was stopped during calibration; agent-v3-1 hit a 5-second shell timeout. The final agent instructions required a 120-second tool timeout. Earlier Notepad warm-ups are setup diagnostics only.

This was not a test of the official ChatGPT desktop Computer Use plugin, nor of full MPMB character creation, class dialogs, spell-page generation, imports, or complete compatibility. The tested programmable worker was standalone Windows Codex app-server using the same custom desktop helper as the direct route.

## Connection and cleanup

SSH endpoint: mpmb-test@127.0.0.1, port 2222, identity ~/.ssh/mpmb_win_vm. The private key stayed on Fedora. The user installed its public key in Windows during setup.

The helper runs in interactive Windows session 1 through an on-demand scheduled task, while SSH/app-server run in session 0. This is how the control path reaches the visible Acrobat desktop.

Both benchmark desktop tasks were stopped after measurement and left registered for reuse. They have no recurring trigger. Portable Codex and benchmark scripts remain in C:\Users\mpmb-test\MPMB-Bench. The helper can be restarted explicitly with `Start-ScheduledTask MPMB-Benchmark-Acrobat`; further production work should first add state verification and reliable text entry. The original local MPMB PDFs were not edited.

## Evidence and reusable harness

- [Raw measured timings, action traces and token counts](~/VirtualMachines/mpmb-windows11/benchmarks/results-v4.json)
- [Independent field/widget verification, expected values and SHA-256 hashes](~/VirtualMachines/mpmb-windows11/benchmarks/verification.json)
- [Saved-PDF render contact sheet](~/VirtualMachines/mpmb-windows11/benchmarks/pdf-render-evidence.png)
- [Acrobat reopen screenshot contact sheet](~/VirtualMachines/mpmb-windows11/benchmarks/screenshot-evidence.png)
- [Host benchmark runner](~/VirtualMachines/mpmb-windows11/benchmarks/benchmark.py)
- [SSH app-server protocol client](~/VirtualMachines/mpmb-windows11/benchmarks/rpc.py)
- [Interactive Windows helper](~/VirtualMachines/mpmb-windows11/benchmarks/acrobat-worker.ps1)
- [Windows job invocation bridge](~/VirtualMachines/mpmb-windows11/benchmarks/invoke-job.ps1)
- [Independent verifier](~/VirtualMachines/mpmb-windows11/benchmarks/verify.py)

Recommendation: build the project's routine regression tests around the direct route with verified input and output. Use a Windows Codex worker for investigations requiring a second agent's reasoning after its tools can verify state. The present unverified macro should not be used as a compatibility oracle.
