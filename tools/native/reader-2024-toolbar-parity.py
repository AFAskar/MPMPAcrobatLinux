#!/usr/bin/env python3
"""Real Adobe Acrobat Reader vs Native parity for 2024 toolbar/utility/format/color/mobile APIs.

Runs the exact same workflow-startup-input observer and original MPMB commands
in both the native runtime and real Adobe Acrobat Reader, checks live console
sentinels, verifies saved PDF canonical fields, formatted AP text for ALlog
dates/currency, non-BMP Unicode notes, Highlighting fillColor, MakeMobileReady
cold reopen, and mixed-engine Native reopening of Reader's saved PDFs.
"""
import argparse
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

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/acrobat"), str(ROOT / "tools/native")]
import control as c
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as closing
from reference_2024_qualification import require_2024_reference
from verify import canonical_fields, inspect, script_hashes
from workflow_state_comparison import encoded_state

CONSOLE_SENTINEL = "MPMB 2024 toolbar parity console sentinel"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/native" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scp_to_windows(local_path, remote_win_path):
    filename = remote_win_path.replace("\\", "/").split("/")[-1]
    remote_dir = "MPMB-Testing/runs/" + filename
    target = os.environ.get("MPMB_WIN_SCP_TARGET", "mpmb-test@127.0.0.1")
    subprocess.run(
        c.SCP + [str(local_path), f"{target}:{remote_dir}"],
        check=True,
        capture_output=True,
    )


def run_native_probe(binary, pdf, scenario, folder, label, timeout=300):
    spec = folder / f"{label}-scenario.json"
    evidence = folder / f"{label}-report.json"
    log = folder / f"{label}.log"
    spec.write_text(json.dumps(scenario, indent=2))
    with log.open("w") as out:
        proc = subprocess.run(
            [str(binary), str(pdf), "--probe", str(spec), str(evidence)],
            cwd=ROOT,
            stdout=out,
            stderr=out,
            timeout=timeout,
        )
    data = json.loads(evidence.read_text())
    assert proc.returncode == 0 and data.get("passed") is True, (label, data.get("error"), str(log))
    assert not data["diagnostics"]["errors"], (label, data["diagnostics"]["errors"])
    msgs = [
        (m["text"] if isinstance(m, dict) else str(m)).rstrip("\r\n")
        for m in data["diagnostics"]["console"]["messages"]
    ]
    assert msgs == [CONSOLE_SENTINEL], (label, msgs)
    return data


def read_payload(pdf):
    fields = canonical_fields(PdfReader(pdf))
    raw = fields["PC Name"]["/V"]
    data = json.loads(raw)
    assert data.pop("sentinel", None) == "\u00a0\u2028\U0001f600", "Missing Unicode sentinel"
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()

    reference = require_2024_reference(json.loads(args.readiness.read_text()), c.harness_fingerprint())
    console_mod = load_module("reader_console", "reader-console.py")
    style = load_module("reader_style", "default-style-persistence.py")

    out = ROOT / "output/testing" / f"reader-2024-toolbar-parity-{time.time_ns()}"
    out.mkdir(parents=True)
    print(out, flush=True)

    # 1. Create disclosed startup-observer input PDF
    fixture_item = next(
        x for x in json.loads((ROOT / "docs/fixtures.json").read_text()) if "_2024_" in x["file"]
    )
    orig_pdf = ROOT / "Testing" / fixture_item["file"]
    assert sha256_file(orig_pdf) == fixture_item["sha256"]
    prep = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/native/prepare-workflow-observer.py"),
            "--input",
            str(orig_pdf),
            "--observer",
            str(ROOT / "tools/native/toolbar-2024-observer.js"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    manifest_path = Path(prep.stdout.strip().splitlines()[-1])
    manifest = json.loads(manifest_path.read_text())
    source = Path(manifest["input"]).resolve()
    expected_scripts = script_hashes(source)
    binary = out / "mpmb-reader"
    shutil.copy2(args.binary.resolve(), binary)
    binary_sha = sha256_file(binary)

    # 2. Run Native phases (create + cold reopen + unmobile)
    nat_s1 = out / "native-phase1-mobile.pdf"
    nat_s2 = out / "native-phase2-unmobile.pdf"
    notes_expr = "toUni('Bold2024','bold')+' \\ud83d\\udd25'"
    nat_steps_1 = [
        {"op": "advance", "ms": 4100},
        {"op": "eval", "code": "__host.command(\"DoTemplate('ALlog','Add',null,true)\")"},
        {"op": "advance", "ms": 500},
        {
            "op": "eval",
            "code": (
                "Value('DateFormat_Remember','d mmm yyyy');"
                "Value('Decimal Separator','comma');"
                "var pre=What('Template.extras.ALlog').split(',').slice(1)[0];"
                "getField(pre+'AdvLog.1.date').value='2024-03-06';"
                "getField(pre+'AdvLog.1.gold.gain').value='1200+34.5';"
                "true"
            ),
        },
        {"op": "advance", "ms": 500},
        {"op": "eval", "code": diagnostics.native_request()},
        {"op": "eval", "code": "Value('User Script','');true"},
        {"op": "save", "path": str(nat_s1)},
    ]
    run_native_probe(
        binary,
        source,
        {"dialogs": [{"result": "ok"}] * 10, "alerts": [1] * 20, "steps": nat_steps_1},
        out,
        "native-p1",
    )
    assert script_hashes(nat_s1) == expected_scripts
    nat_state_1 = read_payload(nat_s1)

    nat_steps_2 = [
        {"op": "advance", "ms": 4100},
        {"op": "eval", "code": diagnostics.native_request()},
        {"op": "eval", "code": "Value('User Script','');true"},
        {"op": "save", "path": str(nat_s2)},
    ]
    run_native_probe(
        binary,
        nat_s1,
        {"dialogs": [{"result": "ok"}] * 10, "alerts": [1] * 20, "steps": nat_steps_2},
        out,
        "native-p2",
    )
    assert script_hashes(nat_s2) == expected_scripts
    nat_state_2 = read_payload(nat_s2)
    print("Native toolbar parity phases 1 & 2: PASS", flush=True)

    # 3. Run Real Adobe Acrobat Reader phases 1 & 2
    run_tag = f"toolbar24-{time.time_ns()}"
    base = c.remote_path("runs/" + run_tag)
    remote = base + ".pdf"
    opened = False
    report = {
        "passed": False,
        "binary": str(args.binary.resolve()),
        "binary_sha256": binary_sha,
        "readiness": str(args.readiness.resolve()),
        "reference": reference,
        "input": str(source),
        "input_sha256": sha256_file(source),
        "native_states": {"phase1": nat_state_1, "phase2": nat_state_2},
        "reader_states": {},
        "console_checks": [],
        "mixed_native": None,
        "display_checks": {},
    }

    def installed():
        deadline = time.monotonic() + 60
        while True:
            marker = c.script("read", path=remote, fields=["User Script"])["fields"]["User Script"]
            if marker == "// MPMB workflow observer installed":
                return
            assert time.monotonic() < deadline, ("Observer installation timeout", marker)
            time.sleep(0.25)

    def check_console():
        c.script("set", path=remote, values={"User Script": "// MPMB workflow console request"})
        deadline = time.monotonic() + 30
        while True:
            rows = c.command("inspect")
            roots = [r for r in rows if r["class"] == "#32770" and r["name"] == "JavaScript Debugger"]
            if roots:
                break
            assert time.monotonic() < deadline, "Console debugger did not appear"
            time.sleep(0.2)
        owner = roots[0]["handle"]
        edits = [r for r in rows if r["owner"] == owner and r["class"] == "RICHEDIT50W"]
        observed = console_mod.read_console_text(owner, edits[0]["handle"])
        report["console_checks"].append(observed)
        observed["close"] = console_mod.close_console(observed)
        assert observed["live"]["text"].rstrip("\r\n") == CONSOLE_SENTINEL, observed["live"]["text"]

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
                c.script("call", path=remote, name="DoTemplate", args=["ALlog", "Add", None, True])
                al_list = c.script("read", path=remote, fields=["Template.extras.ALlog"])["fields"]["Template.extras.ALlog"]
                al_pre = al_list.split(",")[1]
                c.script("set", path=remote, values={"DateFormat_Remember": "d mmm yyyy", "Decimal Separator": "comma"})
                c.script(
                    "set",
                    path=remote,
                    values={
                        al_pre + "AdvLog.1.date": "2024-03-06",
                        al_pre + "AdvLog.1.gold.gain": "1200+34.5",
                    },
                )

                timer1 = diagnostics.reader_request(c, remote)
                summary1 = c.script("field_summary", path=remote, fields=["PC Name"])["fields"]["PC Name"]
                c.script("set", path=remote, values={"User Script": ""})
                rdr_remote_1 = base + "-phase1-mobile.pdf"
                c.script("save", path=remote, output=rdr_remote_1)
                remote = rdr_remote_1
                rdr_s1 = c.fetch(remote, out / "reader-phase1-mobile.pdf")
                rdr_state_1 = style.saved_capture(rdr_s1, summary1, source)
                assert script_hashes(rdr_s1) == expected_scripts
                check_console()
                report["phase1_close"] = closing.close_saved(c, remote)
                opened = False

                assert encoded_state(rdr_state_1) == encoded_state(nat_state_1), (
                    "Phase 1 Reader vs Native mismatch",
                    rdr_state_1,
                    nat_state_1,
                )
                report["reader_states"]["phase1"] = {"state": rdr_state_1, "timer": timer1, "pdf": str(rdr_s1)}
                print("Reader toolbar parity phase 1 (APIs, ALlog, colors, non-BMP, mobile): PASS", flush=True)

                # Phase 2: Cold Reader reopen -> observer confirms preMobile.active=true then MakeMobileReady(false)
                remote, report["phase2_reopen"] = closing.reopen_snapshot(c, remote)
                opened = True
                c.ensure_document(remote)
                installed()
                timer2 = diagnostics.reader_request(c, remote)
                summary2 = c.script("field_summary", path=remote, fields=["PC Name"])["fields"]["PC Name"]
                c.script("set", path=remote, values={"User Script": ""})
                rdr_remote_2 = base + "-phase2-unmobile.pdf"
                c.script("save", path=remote, output=rdr_remote_2)
                remote = rdr_remote_2
                rdr_s2 = c.fetch(remote, out / "reader-phase2-unmobile.pdf")
                rdr_state_2 = style.saved_capture(rdr_s2, summary2, source)
                assert script_hashes(rdr_s2) == expected_scripts
                check_console()
                report["phase2_close"] = closing.close_saved(c, remote)
                opened = False

                assert encoded_state(rdr_state_2) == encoded_state(nat_state_2), (
                    "Phase 2 Reader vs Native mismatch",
                    rdr_state_2,
                    nat_state_2,
                )
                report["reader_states"]["phase2"] = {"state": rdr_state_2, "timer": timer2, "pdf": str(rdr_s2)}
                print("Reader toolbar parity phase 2 (cold reopen + MakeMobileReady false): PASS", flush=True)
            finally:
                if opened:
                    try:
                        report["cleanup_close"] = closing.close_saved(c, remote)
                        opened = False
                    except Exception as err:
                        report["cleanup_error"] = str(err)

        # Verify actual formatted AP text in BOTH Native and Reader PDFs for ALlog date & comma gold!
        for label, npdf, rpdf in [("phase1", nat_s1, rdr_s1), ("phase2", nat_s2, rdr_s2)]:
            al_pre_chk = nat_state_1["alLog"]["prefix"]
            n_ins = inspect(npdf, {al_pre_chk + "AdvLog.1.date": "2024-03-06", al_pre_chk + "AdvLog.1.gold.gain": "1200+34.5"})
            r_ins = inspect(rpdf, {al_pre_chk + "AdvLog.1.date": "2024-03-06", al_pre_chk + "AdvLog.1.gold.gain": "1200+34.5"})
            n_date_ap = [w["appearance_text"].strip() for w in n_ins["widgets"] if w["name"] == al_pre_chk + "AdvLog.1.date"]
            r_date_ap = [w["appearance_text"].strip() for w in r_ins["widgets"] if w["name"] == al_pre_chk + "AdvLog.1.date"]
            n_gold_ap = [w["appearance_text"].strip() for w in n_ins["widgets"] if w["name"] == al_pre_chk + "AdvLog.1.gold.gain"]
            r_gold_ap = [w["appearance_text"].strip() for w in r_ins["widgets"] if w["name"] == al_pre_chk + "AdvLog.1.gold.gain"]
            assert n_date_ap == r_date_ap == ["6 Mar 2024"], (label, n_date_ap, r_date_ap)
            assert n_gold_ap == r_gold_ap == ["1.234,5"], (label, n_gold_ap, r_gold_ap)
            report["display_checks"][label] = {
                "date_ap_native": n_date_ap,
                "date_ap_reader": r_date_ap,
                "gold_ap_native": n_gold_ap,
                "gold_ap_reader": r_gold_ap,
            }

        # 4. Mixed-engine Native reopen of Reader's phase1 mobile PDF -> MakeMobileReady(false) -> compare to phase2!
        mixed_pdf = out / "mixed-native-from-reader-p1.pdf"
        run_native_probe(
            binary,
            rdr_s1,
            {"dialogs": [{"result": "ok"}] * 10, "alerts": [1] * 20, "steps": nat_steps_2[:-1] + [{"op": "save", "path": str(mixed_pdf)}]},
            out,
            "mixed-native",
        )
        assert script_hashes(mixed_pdf) == expected_scripts
        mixed_state = read_payload(mixed_pdf)
        assert encoded_state(mixed_state) == encoded_state(rdr_state_2), (
            "Mixed Native vs Reader phase 2 mismatch",
            mixed_state,
            rdr_state_2,
        )
        report["mixed_native"] = {"passed": True, "pdf": str(mixed_pdf), "state": mixed_state}
        report["passed"] = True
        print("Mixed-engine Native reopen of Reader mobile/color/non-BMP/ALlog PDF: PASS", flush=True)
    finally:
        if opened:
            try:
                closing.close_saved(c, remote)
            except Exception as err:
                report["cleanup_error"] = str(err)
        (out / "toolbar-parity.json").write_text(json.dumps(report, indent=2) + "\n")

    print(out / "toolbar-parity.json", flush=True)


if __name__ == "__main__":
    main()
