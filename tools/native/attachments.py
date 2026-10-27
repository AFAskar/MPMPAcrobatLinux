#!/usr/bin/env python3
"""Verify existing MPMB attachments through original FAQ/helper workflows.

Probe exports are explicit files; requested launches are suppressed and recorded.
This does not qualify attachment import/modification or desktop launch behavior.
"""
import hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields, inspect, script_hashes


def payloads(path):
    return {name: data[0] for name, data in PdfReader(path).attachments.items()}


def main():
    folder = ROOT / 'output/testing' / ('native-attachments-' + str(time.time_ns())); folder.mkdir()
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'cases': []}; print(folder, flush=True)
    try:
        for fixture, pattern in [('2014', '*_2014_*.pdf'), ('2024', '*_2024_*.pdf'), ('ashnar', 'Ashnar*.pdf')]:
            source = next((ROOT / 'Testing').glob(pattern)); original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            dialogs = [{'result': 'ok', 'title': 'SOURCE SELECTION DIALOG'}] if fixture != 'ashnar' else []
            dialogs += [{'title': 'ADD FILE TO ACROBAT INSTALLATION DIALOG', 'event': 'bADD'}, {'title': 'ADD FILE TO ACROBAT INSTALLATION DIALOG', 'result': 'cancel'}]
            output = folder / (fixture + '-saved.pdf')
            steps = [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': "__host.command(\"MakeFaqMenu_FaqOptions('justMenu')\")"}, {'op': 'eval', 'code': "if(!Menus.faq.some(n=>n.cReturn==='faq#pdf'))throw Error('Built-in FAQ menu missing');dataObjects"}, {'op': 'eval', 'code': "__host.command(\"getFAQ(['faq','pdf'])\")"}, {'op': 'eval', 'code': "__host.command('AddFolderJavaScript(false)')"}, {'op': 'save', 'path': str(output)}]
            scenario, evidence = folder / (fixture + '-scenario.json'), folder / (fixture + '-report.json')
            scenario.write_text(json.dumps({'attachment_output_dir': str(folder / fixture), 'dialogs': dialogs, 'alerts': [1] * 20, 'steps': steps}))
            with (folder / (fixture + '.log')).open('w') as log:
                proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)], stdout=log, stderr=log, timeout=240)
            data = json.loads(evidence.read_text()); assert proc.returncode == 0 and data['passed'], data.get('error')
            expected = payloads(source); exports = data['diagnostics']['attachmentExports']; assert len(exports) == 2
            assert set(expected) == {j['name'] for j in exports}
            for job in exports:
                assert job['status'] == 'saved'
                assert Path(job['path']).read_bytes() == expected[job['name']], 'Exported bytes differ'
                assert not job['launched']
                if job['name'] == 'FAQ.pdf':
                    assert job['launch_suppressed']
                    pdf = PdfReader(job['path']); assert len(pdf.pages) > 0
                    subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '900', '-png', job['path'], str(folder / (fixture + '-faq-render'))], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            assert payloads(output) == expected and script_hashes(output) == script_hashes(source)
            before = canonical_fields(PdfReader(source)); after = canonical_fields(PdfReader(output))
            assert set(before) == set(after), 'Saved attachment workflow changed field inventory'
            assert inspect(output, {'PC Name': str(before['PC Name'].get('/V', ''))})['passed']
            reopen, reopened = folder / (fixture + '-reopen.json'), folder / (fixture + '-reopened.json')
            reopen.write_text(json.dumps({'dialogs': [{'result': 'ok'}] * 20, 'alerts': [1] * 20, 'steps': [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': "__host.command(\"MakeFaqMenu_FaqOptions('justMenu')\");if(!Menus.faq.some(n=>n.cReturn==='faq#pdf'))throw Error('Reopened FAQ menu missing');dataObjects"}]}))
            with (folder / (fixture + '-reopen.log')).open('w') as log:
                subprocess.run([str(binary), str(output), '--probe', str(reopen), str(reopened)], check=True, stdout=log, stderr=log, timeout=240)
            r = json.loads(reopened.read_text()); assert r['passed']
            metadata = data['stages'][2]['result']; assert r['stages'][-1]['result'] == metadata
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            report['cases'].append({'fixture': fixture, 'passed': True, 'source': str(source), 'output': str(output), 'metadata': metadata, 'exports': exports, 'probe': str(evidence), 'reopen': str(reopened), 'payloads_equal': True})
            (folder / 'attachments.json').write_text(json.dumps(report, indent=2)); print(fixture, 'attachment exports/persistence PASS', flush=True)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error); raise
    finally:
        (folder / 'attachments.json').write_text(json.dumps(report, indent=2)); print(folder / 'attachments.json', flush=True)

if __name__ == '__main__':
    main()
