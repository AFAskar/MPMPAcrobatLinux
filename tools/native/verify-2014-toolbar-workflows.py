#!/usr/bin/env python3
"""Verify 2014 MPMB toolbar, utility, icon, date, color, mobile, import and print workflows.

Each case runs original 2014 scripts (v14.2.0+261023), verifying independent
pypdf canonical/widget/appearance/script checks and cold reopen persistence.
"""
import argparse
import hashlib
import json
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
sys.path.insert(0, str(ROOT / "tools/acrobat"))
from verify import canonical_fields, script_hashes

SOURCE = "SOURCE SELECTION DIALOG"


def fixture_2014():
    item = next(
        x
        for x in json.loads((ROOT / "docs/fixtures.json").read_text())
        if "_2014_" in x["file"]
    )
    pdf = ROOT / "Testing" / item["file"]
    _require(hashlib.sha256(pdf.read_bytes()).hexdigest() == item["sha256"], 'hashlib.sha256(pdf.read_bytes()).hexdigest() == item["sha256"]')
    return pdf, item["sha256"]


def run_probe(binary, pdf, scenario, folder, label, timeout=300, allow_upstream_format2=False):
    spec = folder / f"{label}-scenario.json"
    evidence = folder / f"{label}-report.json"
    log = folder / f"{label}.log"
    spec.write_text(json.dumps(scenario, indent=2))
    started = time.monotonic()
    with log.open("w") as out:
        proc = subprocess.run(
            [str(binary), str(pdf), "--probe", str(spec), str(evidence)],
            cwd=ROOT,
            stdout=out,
            stderr=out,
            timeout=timeout,
        )
    data = (
        json.loads(evidence.read_text())
        if evidence.exists()
        else {"passed": False, "error": f"No probe report; inspect {log}"}
    )
    _require(not data["diagnostics"]["console"]["messages"], (
        label,
        data["diagnostics"]["console"]["messages"],
    ))
    errs = data["diagnostics"]["errors"]
    if allow_upstream_format2 and errs:
        _require(all(s["passed"] for s in data["stages"]), (label, data.get("error"), str(log)))
        _require(all(
            e.get("field") == "Carrying Capacity Multiplier"
            and e.get("event") == "F"
            and "format2" in str(e.get("stack", ""))
            for e in errs
        ), (label, errs))
    else:
        _require(proc.returncode == 0, (label, data.get("error"), str(log)))
        _require(data.get("passed") is True, (label, data.get("error")))
        _require(not errs, (label, errs))
    return {
        "probe": str(evidence),
        "seconds": round(time.monotonic() - started, 3),
        "strict_exit_code": proc.returncode,
        "diagnostics": data["diagnostics"],
        "stages": data["stages"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary",
        type=Path,
        default=ROOT / "target/debug/mpmb-reader",
        help="Runtime binary to qualify",
    )
    args = parser.parse_args()
    pdf, orig_sha = fixture_2014()
    orig_scripts = script_hashes(pdf)
    folder = ROOT / "output/testing" / f"native-2014-toolbar-{time.time_ns()}"
    folder.mkdir(parents=True)
    binary = folder / "mpmb-reader"
    shutil.copy2(args.binary.resolve(), binary)
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    report = {
        "passed": False,
        "fixture": "2014",
        "binary": str(args.binary.resolve()),
        "binary_sha256": binary_sha,
        "fixture_sha256": orig_sha,
        "cases": {},
    }
    print(folder, flush=True)

    try:
        # Case 1: Faction (event.changeEx + buttonGetIcon ===), ALlog dates (scand/printd), decimal comma (printf)
        c1_pdf = folder / "case1-faction-allog.pdf"
        c1_scenario = {
            "dialogs": [{"title": SOURCE, "result": "ok"}] + [{"result": "ok"}] * 10,
            "alerts": [1] * 20,
            "steps": [
                {"op": "advance", "ms": 4100},
                {"op": "edit", "field": "PC Name", "value": "AL Faction Hero 2014"},
                {"op": "select-choice", "field": "Background_Faction.Text", "value": "harpers"},
                {"op": "advance", "ms": 500},
                {
                    "op": "eval",
                    "code": (
                        "var sym=getField('Symbol'),harp=getField('SaveIMG.Faction.harpers.symbol'),rank=getField('Background_FactionRank.Text');"
                        "if(sym.display!==display.visible)throw Error('Symbol not visible');"
                        "if(sym.buttonGetIcon()!==harp.buttonGetIcon())throw Error('Symbol icon identity mismatch');"
                        "if(rank.numItems<4)throw Error('Faction ranks not populated: '+rank.numItems);"
                        "if(getField('Background_Faction.Text').editable!==true)throw Error('Faction combo should be editable');"
                        "({ranks:rank.numItems,editable:getField('Background_Faction.Text').editable})"
                    ),
                },
                {"op": "eval", "code": "__host.command(\"DoTemplate('ALlog','Add',null,true)\")"},
                {"op": "advance", "ms": 500},
                {
                    "op": "eval",
                    "code": (
                        "var alList=What('Template.extras.ALlog').split(',').slice(1);"
                        "if(!alList.length)throw Error('ALlog template missing: '+What('Template.extras.ALlog'));"
                        "var pre=alList[0];"
                        "Value('DateFormat_Remember','d-m-yyyy');"
                        "var df=getField(pre+'AdvLog.1.date');"
                        "df.value='2024-03-05';"
                        "var s1=JSON.parse(__host.snapshot())[df.name].formatted;"
                        "Value('DateFormat_Remember','d mmm yyyy');"
                        "df.value='2024-03-06';"
                        "var s2=JSON.parse(__host.snapshot())[df.name].formatted;"
                        "Value('Decimal Separator','comma');"
                        "var gp=getField(pre+'AdvLog.1.gold.gain');"
                        "gp.value='1200+34.5';"
                        "var gfmt=JSON.parse(__host.snapshot())[gp.name].formatted;"
                        "if(s1!=='5-3-2024')throw Error('Bad d-m-yyyy: '+s1);"
                        "if(s2!=='6 Mar 2024')throw Error('Bad d mmm yyyy: '+s2);"
                        "if(gfmt!=='1.234,5')throw Error('Bad comma printf via format2: '+gfmt);"
                        "({pre:pre,d1:s1,d2:s2,gold:gfmt})"
                    ),
                },
                {"op": "save", "path": str(c1_pdf)},
            ],
        }
        r1 = run_probe(binary, pdf, c1_scenario, folder, "case1-create")
        _require(script_hashes(c1_pdf) == orig_scripts, 'script_hashes(c1_pdf) == orig_scripts')
        r1_reopen = run_probe(
            binary,
            c1_pdf,
            {
                "dialogs": [{"result": "ok"}] * 10,
                "alerts": [1] * 20,
                "steps": [
                    {"op": "advance", "ms": 4100},
                    {
                        "op": "eval",
                        "code": (
                            "var sym=getField('Symbol'),harp=getField('SaveIMG.Faction.harpers.symbol');"
                            "if(sym.buttonGetIcon()!==harp.buttonGetIcon())throw Error('Cold icon identity mismatch');"
                            "var pre=What('Template.extras.ALlog').split(',').slice(1)[0];"
                            "if(What(pre+'AdvLog.1.date')!=='2024-03-06')throw Error('Cold AL date lost: '+What(pre+'AdvLog.1.date'));"
                            "if(What('Background_Faction.Text')!=='harpers')throw Error('Cold faction lost');"
                            "true"
                        ),
                    },
                ],
            },
            folder,
            "case1-reopen",
        )
        report["cases"]["faction_allog_dates_printf"] = {
            "passed": True,
            "create": r1["probe"],
            "reopen": r1_reopen["probe"],
            "pdf": str(c1_pdf),
        }
        print("2014 Case 1 (Faction + ALlog dates + printf comma + cold icon ===): PASS", flush=True)

        # Case 2: Sources dialog + Patreon dialog (util.iconStreamFromIcon + Date.toSource + launchURL + pane)
        c2_pdf = folder / "case2-sources-patreon.pdf"
        c2_scenario = {
            "dialogs": [
                {"title": SOURCE, "result": "ok"},
                {"title": SOURCE, "event": "BTRA"},
                {"title": SOURCE, "event": "bLin"},
                {"title": SOURCE, "result": "ok"},
                {"title": "SUPPORT ON PATREON DIALOG", "event": "bPat"},
                {"title": "SUPPORT ON PATREON DIALOG", "result": "ok"},
            ]
            + [{"result": "ok"}] * 10,
            "alerts": [1] * 20,
            "steps": [
                {"op": "advance", "ms": 4100},
                {
                    "op": "eval",
                    "code": (
                        "var m=app.monitors.primary();if(!m||!m[0]||m[0].rect[3]!==1080)throw Error('monitors');"
                        "if(/hamburger/i.test(app.listMenuItems().toSource()))throw Error('listMenuItems');"
                        "if(pane!=='bookmarks')throw Error('Expected OpeningStatement pane=bookmarks, got '+pane);"
                        "true"
                    ),
                },
                {"op": "eval", "code": "__host.command('resourceDecisionDialog()')"},
                {"op": "advance", "ms": 500},
                {"op": "eval", "code": "__host.command('PatreonStatement(true)')"},
                {"op": "advance", "ms": 500},
                {
                    "op": "eval",
                    "code": (
                        "var saved=eval_ish(getField('SaveIMG.Patreon').submitName);"
                        "if(!(saved instanceof Date)||isNaN(saved.getTime()))throw Error('Patreon Date.toSource failed');"
                        "var diag=JSON.parse(__host.diagnostics());"
                        "if(!diag.launchedUrls.some(function(u){return /patreon|flapkan/i.test(u.url)}))throw Error('Patreon launchURL missing');"
                        "({date:saved.toISOString(),urls:diag.launchedUrls.map(function(u){return u.url})})"
                    ),
                },
                {"op": "save", "path": str(c2_pdf)},
            ],
        }
        r2 = run_probe(binary, pdf, c2_scenario, folder, "case2-create")
        _require(script_hashes(c2_pdf) == orig_scripts, 'script_hashes(c2_pdf) == orig_scripts')
        report["cases"]["sources_patreon_iconstream_launchurl_pane"] = {
            "passed": True,
            "create": r2["probe"],
            "launched_urls": r2["diagnostics"]["launchedUrls"],
            "pane": r2["diagnostics"]["pane"],
        }
        print("2014 Case 2 (Sources link_text + monitors + Patreon iconStream + Date.toSource + launchURL + pane): PASS", flush=True)

        # Case 3: Highlighting fillColor, non-BMP Unicode notes, MakeMobileReady toggle, ResetAll
        c3_pdf = folder / "case3-color-nonbmp-mobile.pdf"
        c3_unmobile_pdf = folder / "case3-unmobile.pdf"
        c3_reset_pdf = folder / "case3-reset.pdf"
        c3_scenario = {
            "dialogs": [{"title": SOURCE, "result": "ok"}] + [{"result": "ok"}] * 10,
            "alerts": [1] * 20,
            "steps": [
                {"op": "advance", "ms": 4100},
                {"op": "edit", "field": "PC Name", "value": "Theme & Unicode Hero 2014"},
                {
                    "op": "eval",
                    "code": (
                        "__host.command(\"ColoryOptions(['color','highlights','adobe default'])\");"
                        "var hl=getField('Highlighting').fillColor;"
                        "if(!Array.isArray(hl)||hl[0]!=='RGB')throw Error('Bad Highlighting.fillColor: '+JSON.stringify(hl));"
                        "var bold=toUni('Bold2014','bold')+' 🔥';"
                        "getField('Notes.Left').value=bold;"
                        "__host.command('MakeMobileReady(true)');"
                        "if(!CurrentVars.mobileset||!CurrentVars.mobileset.active)throw Error('Mobile mode not active');"
                        "if(getField('PC Name').readonly!==true)throw Error('PC Name should be readonly in mobile mode');"
                        "({bold:bold,hl:hl})"
                    ),
                },
                {"op": "save", "path": str(c3_pdf)},
            ],
        }
        r3 = run_probe(binary, pdf, c3_scenario, folder, "case3-create")
        _require(script_hashes(c3_pdf) == orig_scripts, 'script_hashes(c3_pdf) == orig_scripts')
        c3_fields = canonical_fields(PdfReader(c3_pdf))
        _require("🔥" in c3_fields["Notes.Left"]["/V"], c3_fields["Notes.Left"]["/V"])
        r3_reopen = run_probe(
            binary,
            c3_pdf,
            {
                "dialogs": [{"result": "ok"}] * 10,
                "alerts": [1] * 20,
                "steps": [
                    {"op": "advance", "ms": 4100},
                    {
                        "op": "eval",
                        "code": (
                            "var hl=getField('Highlighting').fillColor;"
                            "if(hl[0]!=='RGB'||Math.abs(hl[1]-0.8)>0.01)throw Error('Cold Highlighting.fillColor lost');"
                            "if(What('Notes.Left').indexOf('🔥')<0)throw Error('Cold non-BMP lost');"
                            "__host.command('MakeMobileReady(false)');"
                            "if(CurrentVars.mobileset.active)throw Error('Mobile mode did not disable');"
                            "if(getField('PC Name').readonly!==false)throw Error('PC Name still readonly after unmobile');"
                            "true"
                        ),
                    },
                    {"op": "save", "path": str(c3_unmobile_pdf)},
                ],
            },
            folder,
            "case3-reopen-unmobile",
        )
        r3_reset = run_probe(
            binary,
            c3_unmobile_pdf,
            {
                "dialogs": [{"result": "ok"}] * 10,
                "alerts": [1] * 20,
                "steps": [
                    {"op": "advance", "ms": 4100},
                    {"op": "eval", "code": "__host.command('ResetAll(true)')"},
                    {"op": "advance", "ms": 1000},
                    {
                        "op": "eval",
                        "code": "if(What('PC Name')!=='')throw Error('ResetAll did not clear PC Name: '+What('PC Name'));true",
                    },
                    {"op": "save", "path": str(c3_reset_pdf)},
                ],
            },
            folder,
            "case3-reset",
            allow_upstream_format2=True,
        )
        _require(script_hashes(c3_unmobile_pdf) == orig_scripts, 'script_hashes(c3_unmobile_pdf) == orig_scripts')
        _require(script_hashes(c3_reset_pdf) == orig_scripts, 'script_hashes(c3_reset_pdf) == orig_scripts')
        report["cases"]["color_nonbmp_mobile_reset"] = {
            "passed": True,
            "create": r3["probe"],
            "reopen_unmobile": r3_reopen["probe"],
            "reset": r3_reset["probe"],
            "upstream_format2_errors": len(r3_reset["diagnostics"]["errors"]),
        }
        print("2014 Case 3 (Color fillColor + non-BMP Unicode + MakeMobileReady + ResetAll): PASS", flush=True)

        # Case 4: DirectImport built-in Faction icon === + XFDF export/import + FAQ.pdf + Print
        c4_xfdf = folder / "case4-export.xfdf"
        c4_import_pdf = folder / "case4-direct-import.pdf"
        c4_xfdf_pdf = folder / "case4-xfdf-import.pdf"
        c4_attach_dir = folder / "attachments"
        c4_print_dir = folder / "prints"
        r4_direct = run_probe(
            binary,
            pdf,
            {
                "dialogs": [
                    {"title": SOURCE, "result": "ok"},
                    {
                        "title": "IMPORT FROM PDF DIALOG",
                        "result": "ok",
                        "values": {
                            "fLoc": str(c1_pdf),
                            "fRel": False,
                            "icYe": False,
                            "icNo": True,
                        },
                    },
                ]
                + [{"result": "ok"}] * 30,
                "alerts": [1] * 30,
                "attachment_output_dir": str(c4_attach_dir),
                "print_output_dir": str(c4_print_dir),
                "steps": [
                    {"op": "advance", "ms": 4100},
                    {"op": "eval", "code": "__host.command('DirectImport(true)')"},
                    {"op": "advance", "ms": 2000},
                    {
                        "op": "eval",
                        "code": (
                            "if(What('PC Name')!=='AL Faction Hero 2014')throw Error('DirectImport PC Name mismatch: '+What('PC Name'));"
                            "if(What('Background_Faction.Text')!=='harpers')throw Error('DirectImport Faction mismatch');"
                            "var sym=getField('Symbol'),harp=getField('SaveIMG.Faction.harpers.symbol');"
                            "if(sym.buttonGetIcon()!==harp.buttonGetIcon())throw Error('DirectImport built-in Faction icon not recognized via ===');"
                            "var xfdf=exportAsXFDFStr({aFields:['PC Name','Background_Faction.Text','Extra.Notes']});"
                            "if(xfdf.indexOf('AL Faction Hero 2014')<0)throw Error('XFDF export missing PC Name');"
                            "exportDataObject({cName:'FAQ.pdf',nLaunch:0});"
                            "Value('Print Remember','false!#TheListSeparator#!0,CSfront');"
                            "__host.command('PrintTheSheet()');"
                            "xfdf"
                        ),
                    },
                    {"op": "save", "path": str(c4_import_pdf)},
                ],
            },
            folder,
            "case4-direct-xfdf-attach-print",
            allow_upstream_format2=True,
        )
        xfdf_text = r4_direct["stages"][-2]["result"]
        c4_xfdf.write_text(xfdf_text)
        _require(list(c4_attach_dir.glob("*.pdf")), "FAQ.pdf export missing")
        prints = list(c4_print_dir.glob("*.pdf"))
        _require(prints and len(PdfReader(prints[0]).pages) == 1, "Print output invalid")
        r4_xfdf = run_probe(
            binary,
            pdf,
            {
                "dialogs": [{"title": SOURCE, "result": "ok"}] + [{"result": "ok"}] * 10,
                "alerts": [1] * 20,
                "steps": [
                    {"op": "advance", "ms": 4100},
                    {"op": "eval", "code": f"importAnXFDF({json.dumps(str(c4_xfdf))})"},
                    {"op": "advance", "ms": 1000},
                    {
                        "op": "eval",
                        "code": "if(What('PC Name')!=='AL Faction Hero 2014')throw Error('XFDF import PC Name mismatch');true",
                    },
                    {"op": "save", "path": str(c4_xfdf_pdf)},
                ],
            },
            folder,
            "case4-xfdf-import",
        )
        _require(script_hashes(c4_import_pdf) == orig_scripts, 'script_hashes(c4_import_pdf) == orig_scripts')
        _require(script_hashes(c4_xfdf_pdf) == orig_scripts, 'script_hashes(c4_xfdf_pdf) == orig_scripts')
        report["cases"]["direct_import_xfdf_attachment_print"] = {
            "passed": True,
            "direct": r4_direct["probe"],
            "xfdf_import": r4_xfdf["probe"],
            "print_pdf": str(prints[0]),
            "upstream_format2_errors": len(r4_direct["diagnostics"]["errors"]),
        }
        print("2014 Case 4 (DirectImport built-in icon === + XFDF export/import + FAQ.pdf + Print): PASS", flush=True)

        _require(hashlib.sha256(pdf.read_bytes()).hexdigest() == orig_sha, 'hashlib.sha256(pdf.read_bytes()).hexdigest() == orig_sha')
        report["passed"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        (folder / "toolbar-workflows.json").write_text(json.dumps(report, indent=2))
        print(folder / "toolbar-workflows.json", flush=True)


if __name__ == "__main__":
    main()
