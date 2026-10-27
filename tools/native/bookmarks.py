#!/usr/bin/env python3
"""Original MPMB bookmark mutation/navigation with independently checked persistence."""
import hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, script_hashes


def main():
    folder = ROOT / 'output/testing' / ('native-bookmarks-' + str(time.time_ns())); folder.mkdir(parents=True)
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases': []}
    print(folder, flush=True)
    def run(source, label, steps):
        spec, evidence = folder / (label + '-scenario.json'), folder / (label + '-report.json')
        spec.write_text(json.dumps({'dialogs': [{'result': 'ok'}] * 10, 'alerts': [1] * 10, 'steps': steps}))
        with (folder / (label + '.log')).open('w') as log:
            result = subprocess.run([str(binary), str(source), '--probe', str(spec), str(evidence)], stdout=log, stderr=log, timeout=180)
        data = json.loads(evidence.read_text())
        assert result.returncode == 0 and data['passed'], data.get('error')
        return str(evidence)
    try:
        for fixture, pattern in [('2014', '*_2014_*.pdf'), ('2024', '*_2024_*.pdf'), ('ashnar', 'Ashnar*.pdf')]:
            source = next((ROOT / 'Testing').glob(pattern)); original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            output = folder / ('bookmarks-' + fixture + '.pdf')
            name = 'Native bookmark audit Ω'
            create = "__host.command(\"functionBookmarks(bookmarkRoot.children[0]);createBookmarks(bookmarkRoot,{'Native bookmark audit Ω':{cExpr: 'getField(\\\"PC Name\\\").value=event.target.name;pageNum=1;',children:{Removed:{cExpr:'pageNum=0'},Retained:{cExpr:'getField(\\\"PC Name\\\").value=event.target.name;pageNum=2;'}}}})\");var b=bookmarkRoot.children[0];b.open=true;b.color=['RGB',0.2,0.3,0.4];b.children[0].remove();b.execute();if(pageNum!==1||What('PC Name')!=='Native bookmark audit Ω')throw Error('Bookmark event/navigation failed');"
            probe = run(source, fixture, [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': create}, {'op': 'save', 'path': str(output)}])
            verified = inspect(output, {'PC Name': name}); assert verified['passed'], verified
            reader = PdfReader(output); outline = reader.trailer['/Root']['/Outlines']; first = outline['/First']; child = first['/First']
            assert first['/Title'] == name and first['/F'] == 2 and first['/Count'] == 1
            assert [round(float(v), 2) for v in first['/C']] == [.2, .3, .4]
            assert child['/Title'] == 'Retained' and '/Next' not in child and child['/Parent'].indirect_reference == first.indirect_reference
            assert first['/A']['/S'] == '/JavaScript' and 'event.target.name' in str(first['/A']['/JS'])
            assert script_hashes(output) == script_hashes(source)
            reopen = run(output, fixture + '-reopen', [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': "var b=bookmarkRoot.children[0];if(b.name!=='Native bookmark audit Ω'||!b.open||b.style!==2||b.children.length!==1||b.children[0].name!=='Retained')throw Error('Bookmark tree not retained');b.children[0].execute();if(pageNum!==2||What('PC Name')!=='Retained')throw Error('Reopened action/event failed');"}])
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            report['cases'].append({'fixture': fixture, 'passed': True, 'probe': probe, 'reopen': reopen, 'output': str(output), 'expected': {'PC Name': name}})
            (folder / 'bookmarks.json').write_text(json.dumps(report, indent=2)); print(fixture, 'bookmark workflow PASS', flush=True)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error); raise
    finally:
        (folder / 'bookmarks.json').write_text(json.dumps(report, indent=2)); print(folder / 'bookmarks.json', flush=True)

if __name__ == '__main__':
    main()
