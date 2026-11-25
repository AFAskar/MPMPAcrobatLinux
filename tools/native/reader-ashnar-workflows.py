#!/usr/bin/env python3
"""Real Adobe Acrobat Reader parity + mixed-engine reopen for legacy Ashnar workflows.

Requires a full 24-case 3-fixture readiness report covering 2014, 2024 and Ashnar.
Runs the exact same 5 Ashnar real-table phases in Real Adobe Acrobat Reader with
live debugger console sentinels, cold reopen, exact byte-for-byte preservation of
the 4+ MiB User_Imported_Files.Stringified payload and all 38 spells.remember.*
fields, exact typed JSON comparison against verify-ashnar-workflows.py, optional
verify-paired-feature-displays.py, and a mixed-engine Native follow-up edit
(Wis 20 -> 22, AC 27 -> 28) on Reader's final saved PDF.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from pypdf import PdfReader

def _require(condition, message=None):
    if not condition:
        raise AssertionError(message)


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/acrobat"), str(ROOT / "tools/native")]
import control as c
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as closing
import subclass_audit_qualification as qualification
from reference_2024_qualification import require_fixture_reference
from verify import canonical_fields, inspect, script_hashes
from workflow_state_comparison import encoded_state

CONSOLE_SENTINEL = "MPMB Ashnar workflow console sentinel"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/native" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def imported_and_spell_digests(pdf_path):
    fields = canonical_fields(PdfReader(pdf_path))
    imported = str(fields.get("User_Imported_Files.Stringified", {}).get("/V", ""))
    remembered = {
        k: str(v.get("/V", ""))
        for k, v in sorted(fields.items())
        if "spells.remember." in k
    }
    return {
        "imported_len": len(imported),
        "imported_sha256": sha256_bytes(imported.encode("utf-8")),
        "remembered_count": len(remembered),
        "remembered_sha256": sha256_bytes(json.dumps(remembered, sort_keys=True).encode("utf-8")),
    }


def require_full_three_fixture_reference(readiness_path):
    ref = require_fixture_reference(json.loads(readiness_path.read_text()), c.harness_fingerprint(), "ashnar")
    return dict(ref, readiness=str(readiness_path.resolve()))


def scp_to_windows(local_path, remote_win_path):
    filename = remote_win_path.replace("\\", "/").split("/")[-1]
    remote_dir = "MPMB-Testing/runs/" + filename
    target = c.SCP_TARGET
    subprocess.run(
        c.SCP + [str(local_path), f"{target}:{remote_dir}"],
        check=True,
        capture_output=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True, help="report.json from verify-ashnar-workflows.py")
    parser.add_argument("--readiness", type=Path, required=True, help="Full 24-case 3-fixture readiness report")
    parser.add_argument("--binary", type=Path, default=ROOT / "target/debug/mpmb-reader")
    parser.add_argument("--skip-paired-display", action="store_true")
    args = parser.parse_args()

    reference = require_full_three_fixture_reference(args.readiness)
    native = json.loads(args.native.read_text())
    _require(native["passed"] is True, "Native Ashnar report must pass first")
    wanted = {p["label"]: p["state"] for p in native["phases"]}
    source = Path(native["input"]).resolve()
    _require(sha256_file(source) == native["input_sha256"], 'sha256_file(source) == native["input_sha256"]')
    expected_scripts = script_hashes(source)
    orig_digests = native["original_payload_digests"]

    style = load_module("ashnar_style", "default-style-persistence.py")
    console_mod = load_module("ashnar_console", "reader-console.py")
    fields_mod = load_module("ashnar_fields", "field-state-comparison.py")
    profile_mod = load_module("ashnar_profile", "fighter-styles.py")

    out = ROOT / "output/testing" / f"reader-ashnar-workflows-{time.time_ns()}"
    out.mkdir(parents=True)
    binary = out / "mpmb-reader"
    shutil.copy2(args.binary.resolve(), binary)
    print(out, flush=True)

    run_tag = f"ashnar-{time.time_ns()}"
    base = c.remote_path("runs/" + run_tag)
    remote = base + ".pdf"
    opened = False

    report = {
        "passed": False,
        "fixture": "ashnar",
        "native": str(args.native.resolve()),
        "reference": reference,
        "input": str(source),
        "input_sha256": native["input_sha256"],
        "binary": str(args.binary.resolve()),
        "binary_sha256": sha256_file(binary),
        "phases": [],
        "console_checks": [],
        "mixed_native": None,
        "paired_display": None,
    }

    MPMB_MODAL_DIALOGS = {
        "ASK USER DIALOG",
        "CHANGES ALERT DIALOG",
        "SOURCE SELECTION DIALOG",
        "SPELL SELECTION DIALOG",
        "SPELL LIST GENERATION DIALOG",
        "CLASS SELECTION DIALOG",
    }

    def installed():
        deadline = time.monotonic() + 90
        while True:
            marker = c.script("read", path=remote, fields=["User Script"])["fields"]["User Script"]
            if marker == "// MPMB workflow observer installed":
                return
            _require(time.monotonic() < deadline, ("Observer installation timeout", marker))
            time.sleep(0.25)

    def check_console():
        c.script("set", path=remote, values={"User Script": "// MPMB workflow console request"})
        deadline = time.monotonic() + 30
        while True:
            rows = c.command("inspect")
            roots = [r for r in rows if r["class"] == "#32770" and r["name"] == "JavaScript Debugger"]
            if roots:
                break
            _require(time.monotonic() < deadline, "Console debugger did not appear")
            time.sleep(0.2)
        owner = roots[0]["handle"]
        edits = [r for r in rows if r["owner"] == owner and r["class"] == "RICHEDIT50W"]
        observed = console_mod.read_console_text(owner, edits[0]["handle"])
        report["console_checks"].append(observed)
        observed["close"] = console_mod.close_console(observed)
        _require(observed["live"]["text"].rstrip("\r\n") == CONSOLE_SENTINEL, observed["live"]["text"])

    def dismiss_modal_dialogs():
        dismissed = []
        rows = c.command("inspect")
        dialogs = [r for r in rows if r["class"] == "#32770" and r["name"] in MPMB_MODAL_DIALOGS]
        for dlg in dialogs:
            btns = [
                b for b in rows
                if b.get("owner") == dlg["handle"] and b["class"] == "Button" and b["name"] in ("OK", "Apply", "Continue", "Yes")
            ]
            if btns:
                c.command("invoke", name=btns[0]["name"], owner=dlg["handle"])
                dismissed.append({"dialog": dlg["name"], "button": btns[0]["name"]})
                time.sleep(0.25)
        return dismissed

    def submit_with_dialogs(op, timeout=240, **params):
        c.ensure_document(remote)
        ident = c.script_submit(op, path=remote, **params)
        deadline = time.monotonic() + timeout
        dismissed = []
        while True:
            dismissed.extend(dismiss_modal_dialogs())
            try:
                return {"result": c.script_result(ident, timeout=10), "dismissed_dialogs": dismissed}
            except RuntimeError as err:
                if time.monotonic() >= deadline:
                    raise
                found = dismiss_modal_dialogs()
                dismissed.extend(found)
                if "timed out" not in str(err).lower() and not found:
                    raise

    def capture(label):
        nonlocal remote
        timer = diagnostics.reader_request(c, remote)
        summary = c.script("field_summary", path=remote, fields=["PC Name"])["fields"]["PC Name"]
        c.script("set", path=remote, values={"User Script": ""})
        output = base + "-" + label + ".pdf"
        c.script("save", path=remote, output=output)
        remote = output
        pdf = c.fetch(remote, out / f"{label}.pdf")
        observed = style.saved_capture(pdf, summary, source)
        _require(encoded_state(observed) == encoded_state(wanted[label]), (
            label,
            "Reader vs Native Ashnar mismatch",
        ))
        _require(script_hashes(pdf) == expected_scripts, 'script_hashes(pdf) == expected_scripts')
        digests = imported_and_spell_digests(pdf)
        _require(digests == orig_digests, (label, "Ashnar imported/spell payload changed in Reader", digests))
        canonical = fields_mod.compare(pdf, dict(observed["fields"], **observed["resources"]))
        pt = {
            "label": label,
            "pdf": str(pdf),
            "pdf_sha256": sha256_file(pdf),
            "state": observed,
            "timer": timer,
            "payload_digests": digests,
            "canonical": canonical,
        }
        report["phases"].append(pt)
        (out / "progress.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"READER Ashnar {label}: PASS", flush=True)
        return pt

    try:
        with c.desktop_lock():
            try:
                _require(not [
                    r for r in c.command("inspect")
                    if r["class"] == "AcrobatSDIWindow" and ".pdf" in r["name"].lower()
                ], "Pre-existing Reader document")
                scp_to_windows(source, remote)
                opened = True
                c.ensure_document(remote)
                installed()

                # Phase 1: Baseline
                capture("ashnar-baseline")

                # Phase 2: Combat spend, damage, notes, selective short rest
                for field_name, field_value in [
                    ("Limited Feature Used 1", "9"),
                    ("Limited Feature Used 2", "1"),
                    ("Limited Feature Used 3", "1"),
                    ("HP Current", "38"),
                    ("HP Temp", "5"),
                    ("HD1 Used", "3"),
                    ("P5.ASnotes.Notes.Left", "Ashnar session note: shadow ambush"),
                ]:
                    c.script("set", path=remote, values={field_name: field_value})
                submit_with_dialogs("call", name="resetLimFeaUsed", args=["short rest"])
                capture("ashnar-combat-spend-short-rest")

                # Phase 3: Long rest, heal, level 12 -> 13
                submit_with_dialogs("call", name="resetLimFeaUsed", args=["long rest"])
                submit_with_dialogs("call", name="HealItNow", args=[])
                submit_with_dialogs("call", name="ApplyClasses", args=["Monk (Way of Shadow) 13", False])
                capture("ashnar-long-rest-heal-level13")
                check_console()

                # Phase 4: Cold close & reopen in Reader
                report["cold_close"] = closing.close_saved(c, remote)
                opened = False
                remote, report["cold_reopen"] = closing.reopen_snapshot(c, remote)
                opened = True
                c.ensure_document(remote)
                installed()
                capture("ashnar-level13-cold")

                # Phase 5: Level 14 Diamond Soul
                submit_with_dialogs("call", name="ApplyClasses", args=["Monk (Way of Shadow) 14", False])
                capture("ashnar-level14-diamond-soul")
                check_console()

                c.script("set", path=remote, values={"User Script": ""})
                final_remote = base + "-final.pdf"
                c.script("save", path=remote, output=final_remote)
                remote = final_remote
                report["final_close"] = closing.close_saved(c, remote)
                opened = False
                reader_final = c.fetch(remote, out / "reader-final.pdf")
                report["reader_final_pdf"] = str(reader_final)
            finally:
                if opened:
                    try:
                        report["cleanup_close"] = closing.close_saved(c, remote)
                        opened = False
                    except Exception as cerr:
                        report["cleanup_error"] = str(cerr)

        # Mixed-Engine Native Reopen of Reader's Level 14 Ashnar -> edit Wis 20 -> 22 (AC 27 -> 28) -> save!
        mixed_pdf = out / "further-native-changed.pdf"
        mixed_spec = out / "further-native-scenario.json"
        mixed_probe = out / "further-native-probe.json"
        mixed_steps = [
            {"op": "advance", "ms": 5100},
            {"op": "assert", "values": {"User Script": "// MPMB workflow observer installed"}},
            {"op": "edit", "field": "Wis", "value": "22"},
            {"op": "advance", "ms": 1000},
            {"op": "assert", "values": {"Wis": "22", "Wis Mod": "6", "AC": "28", "Character Level": "14"}},
            {"op": "eval", "code": diagnostics.native_request()},
            {"op": "eval", "code": profile_mod.SUMMARY},
            {"op": "eval", "code": "Value('User Script','');true"},
            {"op": "save", "path": str(mixed_pdf)},
        ]
        mixed_spec.write_text(
            json.dumps({"steps": mixed_steps, "dialogs": [{"result": "ok"}] * 20, "alerts": [1] * 20}, indent=2)
        )
        with (out / "further-native.log").open("w") as f_out:
            proc = subprocess.run(
                [str(binary), str(reader_final), "--probe", str(mixed_spec), str(mixed_probe)],
                cwd=ROOT,
                stdout=f_out,
                stderr=f_out,
                timeout=300,
            )
        mdata = json.loads(mixed_probe.read_text())
        msgs = mdata["diagnostics"]["console"]["messages"]
        _require([m["text"] for m in msgs] == [CONSOLE_SENTINEL], ("mixed", msgs))
        strict = copy.deepcopy(mdata)
        strict["diagnostics"]["console"]["messages"] = []
        mchecked = qualification.qualify_probe(proc.returncode, strict, "further-native")
        _require(mchecked["passed"], mchecked)
        _require(script_hashes(mixed_pdf) == expected_scripts, 'script_hashes(mixed_pdf) == expected_scripts')
        _require(imported_and_spell_digests(mixed_pdf) == orig_digests, 'imported_and_spell_digests(mixed_pdf) == orig_digests')
        mixed_expected = {"Wis": "22", "Wis Mod": "6", "AC": "28", "Character Level": "14"}
        mixed_inspect = inspect(mixed_pdf, mixed_expected)
        _require(mixed_inspect["actual"] == mixed_expected, ("Ashnar mixed canonical mismatch", mixed_inspect["actual"]))
        for fname in mixed_expected:
            vis = [w for w in mixed_inspect["widgets"] if w["name"] == fname and w["visible"]]
            _require(vis and all((w.get("appearance_text") or "").strip() for w in vis), ("Ashnar mixed missing visible AP", fname))
        report["mixed_native"] = {
            "passed": True,
            "pdf": str(mixed_pdf),
            "pdf_sha256": sha256_file(mixed_pdf),
            "probe": str(mixed_probe),
            "verified_fields": mixed_expected,
        }

        from profile_qualification import finalize_profile_qualification

        finalize_profile_qualification(
            report,
            out,
            args.native,
            source,
            skip_paired_display=args.skip_paired_display,
            timeout=1800,
        )
        status = "PASS" if report["passed"] else "CAPTURE-ONLY (paired display deferred)"
        print(f"READER+MIXED Ashnar (5 phases + Wis 20->22 mixed reopen): {status}", flush=True)
    except Exception as err:
        report["passed"] = False
        report["error"] = str(err)
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(out / "report.json", flush=True)


if __name__ == "__main__":
    main()
