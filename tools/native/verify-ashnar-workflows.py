#!/usr/bin/env python3
"""Verify real-world table workflows on the legacy Ashnar fixture (v14.0.2-beta+251205).

Exercises cold load with 4+ MiB imported user add-on scripts, combat resource
spending, selective short rest vs long rest, healing, spawned notes editing,
level 12->13 progression, cold reopen, and level 14 Diamond Soul progression,
verifying exact preservation of all original scripts, imported user payloads,
and remembered spell fields across every saved snapshot.
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
import fighter_additional_diagnostics as diagnostics
import subclass_audit_qualification as qualification
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


def validate_ashnar_phase(label, state, baseline_st=None):
    _require(not state["errors"], (label, state["errors"]))
    _require(not state["unavailable"], (label, state["unavailable"]))
    f = state["fields"]
    rows_by_prefix = {r["name"]: r for r in state["rows"]}

    def find_row(prefix):
        matches = [r for r in state["rows"] if r["name"].startswith(prefix)]
        _require(len(matches) == 1, (label, prefix, state["rows"]))
        return matches[0]

    if label == "ashnar-baseline":
        _require(f["Character Level"] == "12", f)
        _require(f["Proficiency Bonus"] == "4", f)
        _require(f["AC"] == "27", f)
        _require(f["HP Max"] == "67", f)
        ki = find_row("Ki Points")
        _require(ki["max"] == "13" and ki["used"] == "4", ki)
        _require(find_row("Faerie Fire")["max"] == "1", 'find_row("Faerie Fire")["max"] == "1"')
        _require(find_row("Darkness")["max"] == "1", 'find_row("Darkness")["max"] == "1"')
    elif label == "ashnar-combat-spend-short-rest":
        ki = find_row("Ki Points")
        ff = find_row("Faerie Fire")
        dk = find_row("Darkness")
        _require(ki["used"] == "", ("Short rest should clear Ki Points", ki))
        _require(ff["used"] == "1", ("Short rest must keep Faerie Fire spent", ff))
        _require(dk["used"] == "1", ("Short rest must keep Darkness spent", dk))
        _require(f["HP Current"] == "38", f)
        _require(f["HP Temp"] == "5", f)
        _require(f["HD1 Used"] == "3", f)
        _require("Ashnar session note" in state["notesAndActions"]["P5.ASnotes.Notes.Left"], '"Ashnar session note" in state["notesAndActions"]["P5.ASnotes.Notes.Left"]')
    elif label in ("ashnar-long-rest-heal-level13", "ashnar-level13-cold"):
        _require(f["Character Level"] == "13", f)
        _require(f["Proficiency Bonus"] == "5", f)
        _require(find_row("Faerie Fire")["used"] == "", "Long rest should clear Faerie Fire")
        _require(find_row("Darkness")["used"] == "", "Long rest should clear Darkness")
        _require(f["HP Current"] == "", f["HP Current"])
        _require(f["HP Temp"] == "", f["HP Temp"])
        _require(f["HD1 Used"] == "", f["HD1 Used"])
        _require("Ashnar session note" in state["notesAndActions"]["P5.ASnotes.Notes.Left"], '"Ashnar session note" in state["notesAndActions"]["P5.ASnotes.Notes.Left"]')
    elif label == "ashnar-level14-diamond-soul":
        _require(f["Character Level"] == "14", f)
        _require(f["Proficiency Bonus"] == "5", f)
        # Diamond Soul adds proficiency (+5) to all six saving throws (Con/Int/Wis/Cha newly proficient!)
        if baseline_st is not None:
            for key in ("Con ST Mod", "Int ST Mod", "Wis ST Mod", "Cha ST Mod"):
                _require(int(f[key]) == int(baseline_st[key]) + 5, (key, baseline_st[key], f[key]))
    else:
        raise ValueError(f"Unknown Ashnar phase: {label}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "target/debug/mpmb-reader")
    parser.add_argument("--input", type=Path, help="Pre-prepared workflow-startup-input instrumented PDF")
    parser.add_argument("--instrumentation", type=Path, help="Matching input.json manifest")
    args = parser.parse_args()

    fixture_item = next(
        x for x in json.loads((ROOT / "docs/fixtures.json").read_text()) if "Ashnar" in x["file"]
    )
    orig_pdf = ROOT / "Testing" / fixture_item["file"]
    _require(sha256_file(orig_pdf) == fixture_item["sha256"], 'sha256_file(orig_pdf) == fixture_item["sha256"]')
    orig_digests = imported_and_spell_digests(orig_pdf)

    if args.input and args.instrumentation:
        manifest_path = args.instrumentation.resolve()
        source = args.input.resolve()
    else:
        prep = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/native/prepare-workflow-observer.py"),
                "--input",
                str(orig_pdf),
                "--observer",
                str(ROOT / "tools/native/ashnar-observer.js"),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        manifest_path = Path(prep.stdout.strip().splitlines()[-1])
        source = Path(json.loads(manifest_path.read_text())["input"]).resolve()

    manifest = json.loads(manifest_path.read_text())
    _require(manifest["passed"] and manifest["input_sha256"] == sha256_file(source), 'manifest["passed"] and manifest["input_sha256"] == sha256_file(source)')
    expected_scripts = script_hashes(source)

    style = load_module("ashnar_style", "default-style-persistence.py")
    fields_mod = load_module("ashnar_fields", "field-state-comparison.py")
    profile_mod = load_module("ashnar_profile", "fighter-styles.py")

    out = ROOT / "output/testing" / f"native-ashnar-workflows-{time.time_ns()}"
    out.mkdir(parents=True)
    binary = out / "mpmb-reader"
    shutil.copy2(args.binary.resolve(), binary)
    binary_sha = sha256_file(binary)
    print(out, flush=True)

    report = {
        "passed": False,
        "fixture": "ashnar",
        "original": str(orig_pdf),
        "original_sha256": fixture_item["sha256"],
        "input": str(source),
        "input_sha256": manifest["input_sha256"],
        "instrumentation": str(manifest_path),
        "binary": str(args.binary.resolve()),
        "binary_sha256": binary_sha,
        "original_payload_digests": orig_digests,
        "phases": [],
        "probe_qualifications": [],
    }

    def run_probe(label, pdf_path, steps, capture_specs, baseline_st=None):
        scenario = out / f"{label}-scenario.json"
        probe = out / f"{label}-probe.json"
        log = out / f"{label}.log"
        scenario.write_text(
            json.dumps(
                {
                    "steps": steps,
                    "dialogs": [{"result": "ok"}] * 40,
                    "alerts": [1] * 40,
                },
                indent=2,
            )
        )
        with log.open("w") as f_out:
            proc = subprocess.run(
                [str(binary), str(pdf_path), "--probe", str(scenario), str(probe)],
                cwd=ROOT,
                stdout=f_out,
                stderr=f_out,
                timeout=600,
            )
        data = json.loads(probe.read_text()) if probe.exists() else {"passed": False, "error": f"Missing {probe}"}
        msgs = data.get("diagnostics", {}).get("console", {}).get("messages", [])
        _require([m["text"] for m in msgs] == [CONSOLE_SENTINEL], (label, msgs, data.get("error")))
        strict = copy.deepcopy(data)
        strict["diagnostics"]["console"]["messages"] = []
        checked = qualification.qualify_probe(proc.returncode, strict, label)
        report["probe_qualifications"].append(dict(checked, probe=str(probe), expected_console=msgs))
        _require(checked["passed"], (label, checked))

        results = []
        for cap_label, summary_idx, saved_pdf in capture_specs:
            state = style.saved_capture(saved_pdf, data["stages"][summary_idx]["result"], source)
            validate_ashnar_phase(cap_label, state, baseline_st=baseline_st)
            if cap_label == "ashnar-baseline":
                baseline_st = {k: state["fields"][k] for k in ("Str ST Mod", "Dex ST Mod", "Con ST Mod", "Int ST Mod", "Wis ST Mod", "Cha ST Mod")}
            _require(script_hashes(saved_pdf) == expected_scripts, (cap_label, "script hashes changed"))
            digests = imported_and_spell_digests(saved_pdf)
            _require(digests == orig_digests, (cap_label, "imported/spell payload changed", digests, orig_digests))
            canonical_check = fields_mod.compare(saved_pdf, dict(state["fields"], **state["resources"]))
            populated = {k: v for k, v in state["fields"].items() if str(v).strip()}
            visible_check = inspect(saved_pdf, populated)
            _require(visible_check["actual"] == populated, (cap_label, "canonical mismatch"))
            results.append(
                {
                    "label": cap_label,
                    "pdf": str(saved_pdf),
                    "pdf_sha256": sha256_file(saved_pdf),
                    "state": state,
                    "payload_digests": digests,
                    "canonical": canonical_check,
                    "visible_field_count": len(populated),
                }
            )
        return results, baseline_st

    try:
        steps = [
            {"op": "advance", "ms": 5100},
            {"op": "assert", "values": {"User Script": "// MPMB workflow observer installed"}},
        ]
        capture_specs = []

        def add_capture(cap_label):
            saved_pdf = out / f"{cap_label}.pdf"
            steps.append({"op": "advance", "ms": 500})
            steps.append({"op": "eval", "code": diagnostics.native_request()})
            summary_idx = len(steps)
            steps.append({"op": "eval", "code": profile_mod.SUMMARY})
            steps.append({"op": "eval", "code": "Value('User Script','');true"})
            steps.append({"op": "save", "path": str(saved_pdf)})
            capture_specs.append((cap_label, summary_idx, saved_pdf))

        # Phase 1: Baseline
        add_capture("ashnar-baseline")

        # Phase 2: Combat spend, damage, notes, selective short rest
        steps += [
            {"op": "edit", "field": "Limited Feature Used 1", "value": "9"},
            {"op": "edit", "field": "Limited Feature Used 2", "value": "1"},
            {"op": "edit", "field": "Limited Feature Used 3", "value": "1"},
            {"op": "edit", "field": "HP Current", "value": "38"},
            {"op": "edit", "field": "HP Temp", "value": "5"},
            {"op": "edit", "field": "HD1 Used", "value": "3"},
            {"op": "edit", "field": "P5.ASnotes.Notes.Left", "value": "Ashnar session note: shadow ambush"},
            {"op": "eval", "code": "__host.command(\"resetLimFeaUsed('short rest')\")"},
            {"op": "advance", "ms": 1000},
        ]
        add_capture("ashnar-combat-spend-short-rest")

        # Phase 3: Long rest, heal, level 12 -> 13
        steps += [
            {"op": "eval", "code": "__host.command(\"resetLimFeaUsed('long rest')\")"},
            {"op": "advance", "ms": 1000},
            {"op": "eval", "code": "__host.command('HealItNow()')"},
            {"op": "advance", "ms": 1000},
            {"op": "eval", "code": "__host.command(\"ApplyClasses('Monk (Way of Shadow) 13', false)\")"},
            {"op": "advance", "ms": 1000},
        ]
        add_capture("ashnar-long-rest-heal-level13")

        primary_phases, baseline_st = run_probe("primary", source, steps, capture_specs)
        report["phases"].extend(primary_phases)

        # Phase 4 & 5: Cold reopen saved L13 -> verify -> L14 Diamond Soul
        l13_pdf = Path(primary_phases[-1]["pdf"])
        cold_steps = [
            {"op": "advance", "ms": 5100},
            {"op": "assert", "values": {"User Script": "// MPMB workflow observer installed"}},
            {"op": "eval", "code": diagnostics.native_request()},
        ]
        cold_specs = []
        cold_summary_idx = len(cold_steps)
        cold_pdf = out / "ashnar-level13-cold.pdf"
        cold_steps += [
            {"op": "eval", "code": profile_mod.SUMMARY},
            {"op": "eval", "code": "Value('User Script','');true"},
            {"op": "save", "path": str(cold_pdf)},
        ]
        cold_specs.append(("ashnar-level13-cold", cold_summary_idx, cold_pdf))

        cold_steps += [
            {"op": "eval", "code": "__host.command(\"ApplyClasses('Monk (Way of Shadow) 14', false)\")"},
            {"op": "advance", "ms": 1000},
            {"op": "eval", "code": diagnostics.native_request()},
        ]
        l14_summary_idx = len(cold_steps)
        l14_pdf = out / "ashnar-level14-diamond-soul.pdf"
        cold_steps += [
            {"op": "eval", "code": profile_mod.SUMMARY},
            {"op": "eval", "code": "Value('User Script','');true"},
            {"op": "save", "path": str(l14_pdf)},
        ]
        cold_specs.append(("ashnar-level14-diamond-soul", l14_summary_idx, l14_pdf))

        reopen_phases, _ = run_probe("reopen", l13_pdf, cold_steps, cold_specs, baseline_st=baseline_st)
        _require(encoded_state(reopen_phases[0]["state"]) == encoded_state(primary_phases[-1]["state"]), "Ashnar cold reopen state mismatch")
        report["phases"].extend(reopen_phases)
        _require(sha256_file(orig_pdf) == fixture_item["sha256"], 'sha256_file(orig_pdf) == fixture_item["sha256"]')
        report["passed"] = True
        print(f"Ashnar native workflow ({len(report['phases'])} phases incl. cold reopen + L14 Diamond Soul): PASS", flush=True)
    except Exception as err:
        report["error"] = str(err)
        raise
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(out / "report.json", flush=True)


if __name__ == "__main__":
    main()
