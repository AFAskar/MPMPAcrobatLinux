# Implementation handoff

Prepared on 2026-10-26 (UTC+3). The qualified Acrobat harness is committed as `04ef77a` (`feat(testing): add qualified Windows Acrobat reference harness`). The subsequent documentation commit is the implementation starting HEAD; identify it with `git rev-parse HEAD`. Its scope is the testing environment, not a native reader implementation.

## Current state

- Fedora development tools and the Windows Reader bridge are available locally. The VM uses 4 vCPUs, 4 GiB RAM and Reader 26.2.22031.0 with protocol 3.
- Qualification: 27/27 preflight, 24/24 readiness, 2/2 real file imports and 6/6 post-restart stability cases passed. The clean checkpoint was actually restored and boot-verified.
- After the internet interruption, a fresh 27-check preflight and a 225.892-second smoke passed. All 15 qualified output PDFs and three original fixtures retained their hashes; the interval audit found no new Reader crashes, guest resource exhaustion or host OOM kills.
- No Cargo workspace, native desktop application, PDF engine integration or native compatibility layer exists yet.

Local evidence is intentionally excluded from Git: `output/testing/qualification-final.json`, `output/testing/connectivity-recheck-1793015176.json`, and the run reports referenced by the readiness audit. A fresh clone needs authorized local fixtures and a configured VM; these are not bundled or downloaded automatically. Existing ignored files on this machine are preserved.

## Before changing PDF behavior

Read AGENTS.md and testing-environment.md. Verify the live environment:

```bash
tools/acrobat/run up
tools/acrobat/run smoke
```

Before accepting new oracle results, run preflight and the readiness suite as required by AGENTS.md. Use unique run copies, serialize desktop operations, and independently validate saved outputs. Keep paid PDFs and extracted source local. Do not add them with `git add -f`.

## First development milestone

Inspect the original source and evaluate the PDF engine before committing to an architecture. PDFium is the provisional first candidate; enabling its JavaScript support alone does not provide all MPMB-required Acrobat APIs. Rust may use native PDF/JavaScript dependencies. Keep one authoritative form state and track unsupported APIs explicitly.

Implement a runnable vertical slice that:

1. Opens and renders both local 2014 and 2024 sheets.
2. Executes their original initialization scripts.
3. Supports field editing and dependent calculations.
4. Handles an actual MPMB character-selection dialog.
5. Saves a disposable PDF that reopens correctly in the native application and real Windows Acrobat.

Then extend coverage to companion and wild-shape pages, spell generation, imports and the supplied filled-character regression. Use reference-feature-inventory.json as an initial inventory, not an exhaustive compatibility specification. Compare fields, widgets, appearance streams, embedded scripts, generated pages and saved character state. Stubs and silently ignored errors do not establish compatibility.

Add reproducible native build/run instructions as implementation begins. Keep Rust source and Cargo.lock tracked, generated artifacts ignored, and changes in focused commits. Avoid concurrent large builds or parallel desktop tests on this laptop.

## Baseline checks

The initial commits were checked for Python syntax, shell syntax, JavaScript syntax, valid JSON, staged whitespace, unwanted binary/private artifacts and common credential patterns. Ignore rules were checked against both excluded paths and trackable Rust/source/example files. Functional harness evidence predates these commits; the harness source is unchanged from the qualification fingerprint.

See testing-readiness-audit.md for measured acceptance boundaries and retained failure history; see windows-reference-benchmark.md only for the retired app-server/direct macro comparison.
