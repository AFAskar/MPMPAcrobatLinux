#!/usr/bin/env python3
"""Real Adobe Acrobat Reader parity + mixed-engine save/reopen for 2014 core classes.

Requires a full 24-case 3-fixture readiness report covering 2014, 2024 and Ashnar.
Runs the exact same startup-observer input and original MPMB commands as
verify-2014-classes.py inside real Adobe Acrobat Reader, checks live console
sentinels, compares complete captured typed JSON states byte-for-byte against
native, runs verify-paired-feature-displays.py, and reopens Reader's final saved
PDF in native for a changed mixed-engine save with independent canonical and
visible-appearance verification.
"""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/acrobat"), str(ROOT / "tools/native")]
import control as c
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as closing
import subclass_audit_qualification as qualification
from profiles_2014 import CONSOLE_SENTINEL, PROFILES
from reference_2024_qualification import require_fixture_reference
from verify import inspect, script_hashes
from workflow_state_comparison import encoded_state


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/native" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_full_three_fixture_reference(readiness_path):
    ref = require_fixture_reference(json.loads(readiness_path.read_text()), c.harness_fingerprint(), "2014")
    return dict(ref, readiness=str(readiness_path.resolve()))


def parse_cmd_call(cmd_str):
    m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$", cmd_str)
    assert m, f"Unsupported command syntax for Reader adapter: {cmd_str}"
    fn = m.group(1)
    raw_args = m.group(2).strip()
    if not raw_args:
        return fn, []
    py_expr = re.sub(r"\btrue\b", "True", raw_args)
    py_expr = re.sub(r"\bfalse\b", "False", py_expr)
    py_expr = re.sub(r"\bnull\b", "None", py_expr)
    parsed = ast.literal_eval("(" + py_expr + ",)")
    return fn, list(parsed)


def parse_spend_eval(code):
    m_prefix = re.search(r"indexOf\((\"[^\"]+\")\)===0", code)
    m_amt = re.search(r"value=(\"[^\"]+\")", code)
    assert m_prefix and m_amt, f"Cannot parse spend helper for Reader: {code}"
    return json.loads(m_prefix.group(1)), json.loads(m_amt.group(1))


def scp_to_windows(local_path, remote_win_path):
    filename = remote_win_path.replace("\\", "/").split("/")[-1]
    remote_dir = "MPMB-Testing/runs/" + filename
    target = os.environ.get("MPMB_WIN_SCP_TARGET", "mpmb-test@127.0.0.1")
    subprocess.run(
        c.SCP + [str(local_path), f"{target}:{remote_dir}"],
        check=True,
        capture_output=True,
    )


def run_reader_profile(
    profile_name,
    native_profile_report_path,
    readiness_path,
    reference,
    binary,
    out_root,
    style,
    console_mod,
    fields_mod,
    profile_mod,
    skip_paired_display=False,
):
    native = json.loads(native_profile_report_path.read_text())
    assert native["passed"], (profile_name, "Native report did not pass")
    wanted = {p["label"]: p["state"] for p in native["phases"]}
    source = Path(native["input"]).resolve()
    assert sha256_file(source) == native["input_sha256"]
    expected_scripts = script_hashes(source)
    cfg = PROFILES[profile_name]

    folder = out_root / profile_name
    folder.mkdir(parents=True, exist_ok=True)
    run_tag = f"class14-{profile_name}-{time.time_ns()}"
    base = c.remote_path("runs/" + run_tag)
    remote = base + ".pdf"
    opened = False
    report = {
        "passed": False,
        "fixture": "2014",
        "profile": profile_name,
        "batch": cfg["batch"],
        "native": str(native_profile_report_path.resolve()),
        "readiness": str(readiness_path.resolve()),
        "reference": reference,
        "input": str(source),
        "input_sha256": native["input_sha256"],
        "phases": [],
        "console_checks": [],
        "inputs": [],
        "mixed_native": None,
        "paired_display": None,
    }

    def persist():
        (folder / "progress.json").write_text(json.dumps(report, indent=2) + "\n")

    def installed():
        deadline = time.monotonic() + 60
        while True:
            marker = c.script("read", path=remote, fields=["User Script"])["fields"]["User Script"]
            if marker == "// MPMB workflow observer installed":
                return
            assert time.monotonic() < deadline, ("Observer installation timeout", profile_name, marker)
            time.sleep(0.25)

    def check_console(request=True):
        if request:
            c.script("set", path=remote, values={"User Script": "// MPMB workflow console request"})
        deadline = time.monotonic() + 30
        while True:
            rows = c.command("inspect")
            roots = [r for r in rows if r["class"] == "#32770" and r["name"] == "JavaScript Debugger"]
            if roots:
                break
            assert time.monotonic() < deadline, (profile_name, "Console debugger did not appear")
            time.sleep(0.2)
        assert len(roots) == 1
        owner = roots[0]["handle"]
        edits = [r for r in rows if r["owner"] == owner and r["class"] == "RICHEDIT50W"]
        assert len(edits) == 1
        observed = console_mod.read_console_text(owner, edits[0]["handle"])
        report["console_checks"].append(observed)
        observed["close"] = console_mod.close_console(observed)
        assert observed["live"]["text"].rstrip("\r\n") == CONSOLE_SENTINEL, (
            profile_name,
            observed["live"]["text"],
        )

    pending_ident = None

    MPMB_MODAL_DIALOGS = {
        "ASK USER DIALOG",
        "CHANGES ALERT DIALOG",
        "SOURCE SELECTION DIALOG",
        "SPELL SELECTION DIALOG",
        "SPELL LIST GENERATION DIALOG",
        "CLASS SELECTION DIALOG",
    }

    def dismiss_modal_dialogs():
        dismissed = []
        rows = c.command("inspect")
        dialogs = [
            r
            for r in rows
            if r["class"] == "#32770"
            and r["name"] in MPMB_MODAL_DIALOGS
        ]
        for dlg in dialogs:
            btns = [
                b
                for b in rows
                if b.get("owner") == dlg["handle"]
                and b["class"] == "Button"
                and b["name"] in ("OK", "Apply", "Continue", "Yes")
            ]
            if btns:
                c.command("invoke", name=btns[0]["name"], owner=dlg["handle"])
                dismissed.append({"dialog": dlg["name"], "button": btns[0]["name"]})
                time.sleep(0.25)
        return dismissed

    def submit_with_dialogs(op, timeout=240, **params):
        nonlocal pending_ident
        c.ensure_document(remote)
        ident = c.script_submit(op, path=remote, **params)
        pending_ident = ident
        deadline = time.monotonic() + timeout
        dismissed = []
        while True:
            found = dismiss_modal_dialogs()
            dismissed.extend(found)
            try:
                res = c.script_result(ident, timeout=10)
                pending_ident = None
                return {"result": res, "dismissed_dialogs": dismissed}
            except RuntimeError as err:
                if time.monotonic() >= deadline:
                    raise
                found = dismiss_modal_dialogs()
                dismissed.extend(found)
                if "timed out" not in str(err).lower() and not found:
                    raise

    def execute_ops(ops, last_state):
        for op in ops:
            kind = op[0]
            if kind == "edit":
                if op[1] in ("Str", "Dex", "Con", "Int", "Wis", "Cha"):
                    reply = c.script("set", path=remote, values={op[1]: op[2]})
                else:
                    reply = submit_with_dialogs("set", timeout=240, values={op[1]: op[2]})
                report["inputs"].append({"edit": [op[1], op[2]], "reply": reply})
            elif kind == "cmd":
                fn, fn_args = parse_cmd_call(op[1])
                reply = submit_with_dialogs("call", timeout=240, name=fn, args=fn_args)
                report["inputs"].append({"call": fn, "args": fn_args, "reply": reply})
            elif kind == "eval":
                prefix, amt = parse_spend_eval(op[1])
                assert last_state is not None
                matches = [r for r in last_state["rows"] if r["name"].startswith(prefix)]
                assert len(matches) == 1, (profile_name, prefix, matches)
                field = "Limited Feature Used " + matches[0]["row"]
                reply = c.script("set", path=remote, values={field: amt})
                report["inputs"].append({"spend": [prefix, field, amt], "reply": reply})
            else:
                raise ValueError(f"Unsupported op: {op}")

    def capture(label):
        nonlocal remote
        timer = diagnostics.reader_request(c, remote)
        summary = c.script("field_summary", path=remote, fields=["PC Name"])["fields"]["PC Name"]
        c.script("set", path=remote, values={"User Script": ""})
        output = base + "-" + label + ".pdf"
        c.script("save", path=remote, output=output)
        remote = output
        pdf = c.fetch(remote, folder / f"{label}.pdf")
        observed = style.saved_capture(pdf, summary, source)
        assert encoded_state(observed) == encoded_state(wanted[label]), (
            profile_name,
            label,
            "Reader vs Native 2014 state mismatch",
        )
        assert script_hashes(pdf) == expected_scripts
        canonical = fields_mod.compare(pdf, dict(observed["fields"], **observed["resources"]))
        point = {
            "label": label,
            "pdf": str(pdf),
            "pdf_sha256": sha256_file(pdf),
            "state": observed,
            "timer": timer,
            "canonical": canonical,
        }
        report["phases"].append(point)
        persist()
        return point

    try:
        with c.desktop_lock():
            try:
                assert not [
                    r
                    for r in c.command("inspect")
                    if r["class"] == "AcrobatSDIWindow" and ".pdf" in r["name"].lower()
                ], "Pre-existing Reader document"
                scp_to_windows(source, remote)
                opened = True
                c.ensure_document(remote)
                installed()

                last_state = None
                for phase_label, ops in cfg["phases"]:
                    execute_ops(ops, last_state)
                    pt = capture(phase_label)
                    last_state = pt["state"]
                check_console()

                # Cold close & reopen in Reader
                cold_label = cfg["phases"][-1][0] + "-cold"
                report["cold_close"] = closing.close_saved(c, remote)
                opened = False
                remote, report["cold_reopen"] = closing.reopen_snapshot(c, remote)
                opened = True
                c.ensure_document(remote)
                installed()
                pt_cold = capture(cold_label)

                # Follow-up changed edit in Reader
                follow_label, follow_ops = cfg["mixed_followup"]
                execute_ops(follow_ops, pt_cold["state"])
                pt_follow = capture(follow_label)
                check_console()

                c.script("set", path=remote, values={"User Script": "", "PC Name": f"Reader 2014 {profile_name} final"})
                final_remote = base + "-final.pdf"
                c.script("save", path=remote, output=final_remote)
                remote = final_remote
                report["final_close"] = closing.close_saved(c, remote)
                opened = False
                reader_final_pdf = c.fetch(remote, folder / "reader-final.pdf")
                report["reader_final_pdf"] = str(reader_final_pdf)
            finally:
                if opened:
                    try:
                        if pending_ident:
                            for _ in range(6):
                                dismiss_modal_dialogs()
                                try:
                                    report["cleanup_collected"] = c.script_result(pending_ident, timeout=5)
                                    pending_ident = None
                                    break
                                except RuntimeError:
                                    time.sleep(0.5)
                        rows = c.command("inspect")
                        if any(r["name"] == "JavaScript Debugger" for r in rows):
                            try:
                                check_console(request=False)
                            except Exception as cerr:
                                report["cleanup_console_error"] = str(cerr)
                        if any(r["class"] == "#32768" for r in c.command("inspect")):
                            c.command("keys", keys="{ESC}")
                        retained = base + "-failed-retained.pdf"
                        c.script("save", path=remote, output=retained)
                        report["cleanup_close"] = closing.close_saved(c, retained)
                        opened = False
                        c.fetch(retained, folder / "failed-retained.pdf")
                    except Exception as cerr:
                        report["cleanup_error"] = str(cerr)

        # Further Native Mixed-Engine Reopen & Changed Save on Reader's final PDF (required)
        assert binary is not None, "Mixed-engine native binary is required for Reader class parity"
        mixed_pdf = folder / "further-native-changed.pdf"
        mixed_scenario = folder / "further-native-scenario.json"
        mixed_probe = folder / "further-native-probe.json"
        expected_note = f"Mixed-engine 2014 native follow-up {profile_name}"
        mixed_steps = [
            {"op": "advance", "ms": 5100},
            {"op": "assert", "values": {"User Script": "// MPMB workflow observer installed"}},
            {"op": "edit", "field": "Extra.Notes", "value": expected_note},
            {"op": "advance", "ms": 500},
            {"op": "eval", "code": diagnostics.native_request()},
            {"op": "eval", "code": profile_mod.SUMMARY},
            {"op": "eval", "code": "Value('User Script','');true"},
            {"op": "save", "path": str(mixed_pdf)},
        ]
        mixed_scenario.write_text(
            json.dumps(
                {"steps": mixed_steps, "dialogs": [{"result": "ok"}] * 20, "alerts": [1] * 20},
                indent=2,
            )
        )
        with (folder / "further-native.log").open("w") as out:
            proc = subprocess.run(
                [str(binary), str(reader_final_pdf), "--probe", str(mixed_scenario), str(mixed_probe)],
                cwd=ROOT,
                stdout=out,
                stderr=out,
                timeout=300,
            )
        mdata = json.loads(mixed_probe.read_text())
        msgs = mdata["diagnostics"]["console"]["messages"]
        assert [m["text"] for m in msgs] == [CONSOLE_SENTINEL], (profile_name, "mixed", msgs)
        strict = copy.deepcopy(mdata)
        strict["diagnostics"]["console"]["messages"] = []
        mchecked = qualification.qualify_probe(proc.returncode, strict, "further-native")
        assert mchecked["passed"], (profile_name, mchecked)
        assert script_hashes(mixed_pdf) == expected_scripts
        mixed_summary = mdata["stages"][5]["result"]
        mixed_state = style.saved_capture(mixed_pdf, mixed_summary, source)
        assert mixed_state["notesAndActions"]["Extra.Notes"] == expected_note, (profile_name, "mixed note mismatch")
        assert mixed_state["identity"] == pt_follow["state"]["identity"], (profile_name, "mixed identity mismatch")
        assert mixed_state["fields"] == pt_follow["state"]["fields"], (profile_name, "mixed fields mismatch")
        assert mixed_state["resources"] == pt_follow["state"]["resources"], (profile_name, "mixed resources mismatch")
        assert mixed_state["templates"] == pt_follow["state"]["templates"], (profile_name, "mixed templates mismatch")
        assert mixed_state["pages"] == pt_follow["state"]["pages"], (profile_name, "mixed pages mismatch")
        mixed_expected = {
            "Extra.Notes": expected_note,
            "Character Level": pt_follow["state"]["fields"]["Character Level"],
            "Proficiency Bonus": pt_follow["state"]["fields"]["Proficiency Bonus"],
            "Class and Levels": pt_follow["state"]["fields"]["Class and Levels"],
        }
        mixed_inspect = inspect(mixed_pdf, mixed_expected)
        assert mixed_inspect["actual"] == mixed_expected, (profile_name, "mixed canonical inspect mismatch")
        note_widgets = [w for w in mixed_inspect["widgets"] if w["name"] == "Extra.Notes" and w["visible"]]
        assert note_widgets and all((w.get("appearance_text") or "").strip() for w in note_widgets), (
            profile_name,
            "mixed Extra.Notes missing visible AP",
        )
        report["mixed_native"] = {
            "passed": True,
            "probe": str(mixed_probe),
            "pdf": str(mixed_pdf),
            "pdf_sha256": sha256_file(mixed_pdf),
            "verified_fields": mixed_expected,
            "pages": mixed_state["pages"],
        }

        from profile_qualification import finalize_profile_qualification

        finalize_profile_qualification(
            report,
            folder,
            native_profile_report_path,
            source,
            skip_paired_display=skip_paired_display,
            timeout=3600,
        )
        status = "PASS" if report["passed"] else "CAPTURE-ONLY (paired display deferred)"
        print(f"READER+MIXED 2014 {profile_name} ({len(report['phases'])} phases): {status}", flush=True)
        return report

    except Exception as exc:
        report["passed"] = False
        report["error"] = str(exc)
        raise
    finally:
        (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=ROOT / "target/debug/mpmb-reader")
    parser.add_argument("--batch", choices=["A", "B", "C", "all"], default="all")
    parser.add_argument("--profile", action="append", choices=sorted(PROFILES))
    parser.add_argument("--skip-paired-display", action="store_true")
    args = parser.parse_args()

    reference = require_full_three_fixture_reference(args.readiness)
    native_summary = json.loads((args.native_dir / "classes-2014.json").read_text())
    assert native_summary["passed"], "Native 2014 summary must pass before Reader comparison"

    selected = args.profile or [
        name
        for name in native_summary["selected"]
        if args.batch == "all" or PROFILES[name]["batch"] == args.batch
    ]
    folder = ROOT / "output/testing" / f"reader-2014-classes-{args.batch}-{time.time_ns()}"
    folder.mkdir(parents=True)
    print(folder, flush=True)

    binary = folder / "mpmb-reader"
    shutil.copy2(args.binary.resolve(), binary)

    style = load_module("class_style", "default-style-persistence.py")
    console_mod = load_module("class_console", "reader-console.py")
    fields_mod = load_module("class_fields", "field-state-comparison.py")
    profile_mod = load_module("class_profile", "fighter-styles.py")

    summary = {
        "passed": False,
        "fixture": "2014",
        "batch": args.batch,
        "selected": selected,
        "readiness": str(args.readiness.resolve()),
        "reference": reference,
        "native_dir": str(args.native_dir.resolve()),
        "profiles": {},
    }
    try:
        for name in selected:
            native_report = args.native_dir / name / "report.json"
            res = run_reader_profile(
                name,
                native_report,
                args.readiness,
                reference,
                binary,
                folder,
                style,
                console_mod,
                fields_mod,
                profile_mod,
                skip_paired_display=args.skip_paired_display,
            )
            summary["profiles"][name] = {
                "passed": res["passed"],
                "state_capture_passed": res.get("state_capture_passed", False),
                "paired_display_status": res.get("paired_display_status"),
                "report": str(folder / name / "report.json"),
                "capture_report": res.get("capture_report"),
                "paired_display": res["paired_display"],
                "mixed_native": res["mixed_native"],
            }
        if c.harness_fingerprint() != reference["harness_sha256"]:
            raise AssertionError("Harness fingerprint changed during suite")
        summary["state_capture_passed"] = all(
            p.get("state_capture_passed") is True for p in summary["profiles"].values()
        )
        summary["passed"] = all(p.get("passed") is True for p in summary["profiles"].values())
    except Exception as exc:
        summary["error"] = str(exc)
        raise
    finally:
        (folder / "reader-classes-2014.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(folder / "reader-classes-2014.json", flush=True)


if __name__ == "__main__":
    main()
