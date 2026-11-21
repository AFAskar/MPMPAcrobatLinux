#!/usr/bin/env python3
"""Run comprehensive 2024 core class, multiclass, species, background, feat, spell,
wildshape and companion workflows natively with strict diagnostics, independent pypdf
checks and cold reopen verification.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/acrobat"), str(ROOT / "tools/native")]
from verify import inspect, script_hashes
import fighter_additional_diagnostics as diagnostics
import subclass_audit_qualification as qualification
from profiles_2024 import CONSOLE_SENTINEL, PROFILES, validate_profile_state
from workflow_state_comparison import encoded_state


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/native" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_phase_steps(ops):
    steps = []
    for op in ops:
        kind = op[0]
        if kind == "edit":
            steps.append({"op": "edit", "field": op[1], "value": op[2]})
        elif kind == "cmd":
            steps.append({"op": "eval", "code": "__host.command(" + json.dumps(op[1]) + ")"})
            steps.append({"op": "advance", "ms": 1000})
        elif kind == "eval":
            steps.append({"op": "eval", "code": op[1]})
            steps.append({"op": "advance", "ms": 500})
        else:
            raise ValueError(f"Unknown op kind: {kind}")
    return steps


def run_profile(profile_name, source, instrumentation, binary, out_root, style, profile_mod, fields_mod):
    cfg = PROFILES[profile_name]
    folder = out_root / profile_name
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        "passed": False,
        "profile": profile_name,
        "batch": cfg["batch"],
        "description": cfg["description"],
        "input": str(source),
        "input_sha256": sha256_file(source),
        "instrumentation": str(instrumentation),
        "binary_sha256": sha256_file(binary),
        "phases": [],
        "probe_qualifications": [],
    }
    expected_scripts = script_hashes(source)

    def run_probe(label, pdf_path, steps, capture_specs):
        scenario = folder / f"{label}-scenario.json"
        probe = folder / f"{label}-probe.json"
        log = folder / f"{label}.log"
        scenario.write_text(
            json.dumps(
                {
                    "steps": steps,
                    "dialogs": [{"title": "SOURCE SELECTION DIALOG", "result": "ok"}]
                    + [{"result": "ok"}] * 100,
                    "alerts": [1] * 100,
                },
                indent=2,
            )
        )
        with log.open("w") as out:
            proc = subprocess.run(
                [str(binary), str(pdf_path), "--probe", str(scenario), str(probe)],
                cwd=ROOT,
                stdout=out,
                stderr=out,
                timeout=600,
                env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / f"{label}-dialogs")),
            )
        data = json.loads(probe.read_text()) if probe.exists() else {"passed": False, "error": f"Missing {probe}"}
        messages = data.get("diagnostics", {}).get("console", {}).get("messages", [])
        assert [m["text"] for m in messages] == [CONSOLE_SENTINEL], (profile_name, label, messages, data.get("error"))
        strict = copy.deepcopy(data)
        strict["diagnostics"]["console"]["messages"] = []
        checked = qualification.qualify_probe(proc.returncode, strict, label)
        report["probe_qualifications"].append(dict(checked, probe=str(probe), expected_console=messages))
        assert checked["passed"], (profile_name, label, checked)
        markers = [
            s["result"]
            for s in data["stages"]
            if isinstance(s.get("result"), str) and s["result"].startswith(diagnostics.DONE)
        ]
        assert markers == [diagnostics.DONE + str(i + 1) for i in range(len(capture_specs))], (
            profile_name,
            label,
            markers,
        )
        results = []
        for cap_label, summary_idx, saved_pdf in capture_specs:
            state = style.saved_capture(saved_pdf, data["stages"][summary_idx]["result"], source)
            validate_profile_state(profile_name, cap_label, state)
            assert script_hashes(saved_pdf) == expected_scripts, (profile_name, cap_label, "script hashes changed")
            canonical_check = fields_mod.compare(saved_pdf, dict(state["fields"], **state["resources"]))
            populated = {k: v for k, v in state["fields"].items() if str(v).strip()}
            visible_check = inspect(saved_pdf, populated)
            assert visible_check["actual"] == populated, (profile_name, cap_label, "canonical mismatch")
            missing_ap = [
                w["name"]
                for w in visible_check["widgets"]
                if w["visible"] and (not w["appearance"] or not (w["appearance_text"] or "").strip())
            ]
            assert not missing_ap, (profile_name, cap_label, "missing visible AP text", missing_ap)
            results.append(
                {
                    "label": cap_label,
                    "pdf": str(saved_pdf),
                    "pdf_sha256": sha256_file(saved_pdf),
                    "state": state,
                    "canonical": canonical_check,
                }
            )
        return results

    # Phase run 1: all primary phases in one session
    steps = [
        {"op": "advance", "ms": 5100},
        {"op": "assert", "values": {"User Script": "// MPMB workflow observer installed"}},
    ]
    capture_specs = []
    for phase_label, ops in cfg["phases"]:
        steps.extend(build_phase_steps(ops))
        steps.append({"op": "advance", "ms": 1000})
        steps.append({"op": "eval", "code": diagnostics.native_request()})
        steps.append({"op": "eval", "code": profile_mod.SUMMARY})
        saved_pdf = folder / f"{phase_label}.pdf"
        capture_specs.append((phase_label, len(steps) - 1, saved_pdf))
        steps.append({"op": "save", "path": str(saved_pdf)})

    primary_phases = run_probe("primary", source, steps, capture_specs)
    report["phases"].extend(primary_phases)

    # Phase run 2: cold reopen of last primary PDF + exact logical state equality + mixed_followup edit
    last_phase = primary_phases[-1]
    cold_label = last_phase["label"] + "-cold"
    follow_label, follow_ops = cfg["mixed_followup"]
    cold_steps = [
        {"op": "advance", "ms": 5100},
        {"op": "assert", "values": {"User Script": "// MPMB workflow observer installed"}},
        {"op": "eval", "code": diagnostics.native_request()},
        {"op": "eval", "code": profile_mod.SUMMARY},
    ]
    cold_pdf = folder / f"{cold_label}.pdf"
    cold_caps = [(cold_label, len(cold_steps) - 1, cold_pdf)]
    cold_steps.append({"op": "save", "path": str(cold_pdf)})
    cold_steps.extend(build_phase_steps(follow_ops))
    cold_steps.append({"op": "advance", "ms": 1000})
    cold_steps.append({"op": "eval", "code": diagnostics.native_request()})
    cold_steps.append({"op": "eval", "code": profile_mod.SUMMARY})
    follow_pdf = folder / f"{follow_label}.pdf"
    cold_caps.append((follow_label, len(cold_steps) - 1, follow_pdf))
    cold_steps.append({"op": "save", "path": str(follow_pdf)})

    # Temporarily validate cold state under last_phase's label, then compare byte-for-byte
    reopen_results = []
    scenario = folder / "reopen-scenario.json"
    probe = folder / "reopen-probe.json"
    log = folder / "reopen.log"
    scenario.write_text(
        json.dumps(
            {
                "steps": cold_steps,
                "dialogs": [{"result": "ok"}] * 40,
                "alerts": [1] * 40,
            },
            indent=2,
        )
    )
    with log.open("w") as out:
        proc = subprocess.run(
            [str(binary), last_phase["pdf"], "--probe", str(scenario), str(probe)],
            cwd=ROOT,
            stdout=out,
            stderr=out,
            timeout=600,
            env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / "reopen-dialogs")),
        )
    data = json.loads(probe.read_text())
    messages = data["diagnostics"]["console"]["messages"]
    assert [m["text"] for m in messages] == [CONSOLE_SENTINEL], (profile_name, "reopen", messages)
    strict = copy.deepcopy(data)
    strict["diagnostics"]["console"]["messages"] = []
    checked = qualification.qualify_probe(proc.returncode, strict, "reopen")
    report["probe_qualifications"].append(dict(checked, probe=str(probe), expected_console=messages))
    assert checked["passed"], (profile_name, "reopen", checked)

    cold_state = style.saved_capture(cold_pdf, data["stages"][cold_caps[0][1]]["result"], source)
    assert encoded_state(cold_state) == encoded_state(last_phase["state"]), (
        profile_name,
        "Cold reopen logical state diverged",
    )
    assert script_hashes(cold_pdf) == expected_scripts
    reopen_results.append(
        {
            "label": cold_label,
            "pdf": str(cold_pdf),
            "pdf_sha256": sha256_file(cold_pdf),
            "state": cold_state,
            "canonical": fields_mod.compare(cold_pdf, dict(cold_state["fields"], **cold_state["resources"])),
        }
    )

    follow_state = style.saved_capture(follow_pdf, data["stages"][cold_caps[1][1]]["result"], source)
    validate_profile_state(profile_name, follow_label, follow_state)
    assert script_hashes(follow_pdf) == expected_scripts
    reopen_results.append(
        {
            "label": follow_label,
            "pdf": str(follow_pdf),
            "pdf_sha256": sha256_file(follow_pdf),
            "state": follow_state,
            "canonical": fields_mod.compare(follow_pdf, dict(follow_state["fields"], **follow_state["resources"])),
        }
    )
    report["phases"].extend(reopen_results)
    report["passed"] = True
    (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Profile {profile_name} ({len(report['phases'])} phases incl. cold reopen + follow-up): PASS", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Startup-observer instrumented 2024 PDF")
    parser.add_argument("--instrumentation", type=Path, required=True, help="input.json from prepare-workflow-observer.py")
    parser.add_argument("--binary", type=Path, default=ROOT / "target/debug/mpmb-reader")
    parser.add_argument("--batch", choices=["A", "B", "all"], default="all")
    parser.add_argument("--profile", action="append", choices=sorted(PROFILES))
    args = parser.parse_args()

    source = args.input.resolve()
    manifest = json.loads(args.instrumentation.read_text())
    assert manifest["passed"] and manifest["mode"] == "startup-script-timer"
    assert Path(manifest["input"]).resolve() == source and manifest["input_sha256"] == sha256_file(source)
    assert manifest["observer_sha256"] == sha256_file(ROOT / "tools/native/class-2024-observer.js")
    assert manifest["diagnostic_helper_sha256"] == sha256_file(Path(diagnostics.__file__))

    selected = args.profile or [
        name for name, cfg in PROFILES.items() if args.batch == "all" or cfg["batch"] == args.batch
    ]
    folder = ROOT / "output/testing" / f"native-2024-classes-{time.time_ns()}"
    folder.mkdir(parents=True)
    binary = folder / "mpmb-reader"
    shutil.copy2(args.binary.resolve(), binary)
    print(folder, flush=True)

    style = load_module("class_style", "default-style-persistence.py")
    profile_mod = load_module("class_profile", "fighter-styles.py")
    fields_mod = load_module("class_fields", "field-state-comparison.py")

    summary = {
        "passed": False,
        "batch": args.batch,
        "selected": selected,
        "input": str(source),
        "input_sha256": sha256_file(source),
        "instrumentation": str(args.instrumentation.resolve()),
        "binary_sha256": sha256_file(binary),
        "profiles": {},
    }
    try:
        for name in selected:
            res = run_profile(
                name,
                source,
                args.instrumentation.resolve(),
                binary,
                folder,
                style,
                profile_mod,
                fields_mod,
            )
            summary["profiles"][name] = {
                "passed": res["passed"],
                "report": str(folder / name / "report.json"),
                "phase_count": len(res["phases"]),
            }
        summary["passed"] = True
    except Exception as exc:
        summary["error"] = str(exc)
        raise
    finally:
        (folder / "classes-2024.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(folder / "classes-2024.json", flush=True)


if __name__ == "__main__":
    main()
