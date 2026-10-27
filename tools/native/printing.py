#!/usr/bin/env python3
"""Controlled original MPMB printing. Never submits a physical printer job."""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import script_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', choices=['2014', '2024', 'ashnar'], action='append')
    args = parser.parse_args()
    folder = ROOT / 'output/testing' / ('native-printing-' + str(time.time_ns()))
    folder.mkdir(parents=True)
    report = {'passed': False, 'scope': 'Original PrintTheSheet and PrintButton, all/selected/generated pages, duplex, printable visibility, static outputs, interactive save/reopen. No physical job submitted; Reader output comparison is separate.', 'cases': []}
    print(folder, flush=True)
    try:
        for label, pattern in [('2014', '*_2014_*.pdf'), ('2024', '*_2024_*.pdf'), ('ashnar', 'Ashnar*.pdf')]:
            if args.fixture and label not in args.fixture:
                continue
            source = next((ROOT / 'Testing').glob(pattern))
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            output = folder / (label + '-interactive.pdf')
            # Four real widgets on page 1 exercise every Acrobat display value.
            setup = "var names=['Attack.1.Description','Attack.2.Description','Attack.3.Description','Attack.4.Description'];getField('PC Name').value='PRINTVISIBLE';var sentinels=['PRINTVISIBLE','PRINTHIDDEN','PRINTSCREENONLY','PRINTONLY'];calculate=false;app.calculate=false;for(var i=0;i<4;i++){var f=getField(names[i]);f.value=sentinels[i];f.display=i;}calculate=true;app.calculate=true;"
            steps = [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': setup},
                     {'op': 'eval', 'code': "__host.command(\"Value('Print Remember','false!#TheListSeparator#!0');PrintTheSheet()\")"},
                     {'op': 'eval', 'code': "__host.command(\"Value('Print Remember','true!#TheListSeparator#!0,CSfront');PrintTheSheet()\")"},
                     {'op': 'eval', 'code': "var generatedPrefix=DoTemplate('AScomp','Add',null,true);ApplyCompRace('wolf',generatedPrefix)"},
                     {'op': 'advance', 'ms': 1000},
                     {'op': 'eval', 'code': "__host.command(\"Value('Print Remember','false!#TheListSeparator#!0,AScomp');PrintTheSheet()\")"},
                     {'op': 'eval', 'code': "__host.command(\"Value('Print Remember','false!#TheListSeparator#!0,CSfront');PrintButton()\")"},
                     {'op': 'eval', 'code': "__host.command('PrintButton()')"},
                     {'op': 'eval', 'code': "if(JSON.parse(__host.diagnostics()).printJobs.length!==4)throw Error('cancel printed a job');if(getField('PC Name').valueAsString!=='PRINTVISIBLE')throw Error('print mutated character');"},
                     {'op': 'save', 'path': str(output)}]
            dialogs = [{'result': 'ok', 'title': 'SOURCE SELECTION DIALOG'}] if label != 'ashnar' else []
            # PrintButton must read these settings through its original destroy handler.
            dialogs += [{'result': 'ok', 'title': 'Choose the pages you want to print', 'values': {'Pag1': True, 'Pag2': False, 'Pag3': False, 'Pag4': False, 'Pag5': False, 'Pag6': False, 'Pag7': False, 'Pag8': False, 'Pag9': False, 'Pag0': False, 'Pa10': False, 'dupl': True, 'sing': False}}, {'result': 'cancel', 'title': 'Choose the pages you want to print'}]
            spec = {'print_output_dir': str(folder / label), 'dialogs': dialogs, 'alerts': [1] * 10, 'steps': steps}
            scenario, evidence = folder / (label + '-scenario.json'), folder / (label + '-report.json')
            scenario.write_text(json.dumps(spec))
            with (folder / (label + '.log')).open('w') as log:
                proc = subprocess.run([str(ROOT / 'target/debug/mpmb-reader'), str(source), '--probe', str(scenario), str(evidence)], stdout=log, stderr=log, timeout=240)
            data = json.loads(evidence.read_text())
            assert proc.returncode == 0 and data['passed'], data.get('error')
            jobs = data['diagnostics']['printJobs']
            assert len(jobs) == 4
            for index, job in enumerate(jobs):
                printed = Path(job['path']); reader = PdfReader(printed)
                assert job['status'] == 'saved'
                assert len(reader.pages) == len(job['pages'])
                assert not reader.get_fields()
                assert '/AcroForm' not in reader.trailer['/Root'] and '/Names' not in reader.trailer['/Root']
                assert not script_hashes(printed)
                assert all(not page.get('/Annots') for page in reader.pages)
                text = subprocess.check_output(['pdftotext', str(printed), '-'], text=True)
                if index in [0, 1]:
                    assert 'PRINTVISIBLE' in text and 'PRINTONLY' in text, (index, 'missing printable values')
                    assert 'PRINTSCREENONLY' not in text and 'PRINTHIDDEN' not in text, (index, 'nonprintable value printed')
                if index == 2:
                    assert 'wolf' in text.lower(), 'missing generated companion'
                if index in [1, 3]:
                    assert job['pages'] == [0] and job['duplex'] == 'two-sided-long-edge', job
                    assert reader.trailer['/Root']['/ViewerPreferences']['/Duplex'] == '/DuplexFlipLongEdge'
                rendered = folder / (label + '-print-' + str(index))
                subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '900', '-png', str(printed), str(rendered)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            assert script_hashes(output) == script_hashes(source)
            reopen = folder / (label + '-reopen.json')
            reopen.write_text(json.dumps({'alerts': [1] * 10, 'steps': [{'op': 'advance', 'ms': 4100}, {'op': 'assert', 'values': {'PC Name': 'PRINTVISIBLE'}}]}))
            with (folder / (label + '-reopen.log')).open('w') as log:
                subprocess.run([str(ROOT / 'target/debug/mpmb-reader'), str(output), '--probe', str(reopen), str(folder / (label + '-reopened.json'))], stdout=log, stderr=log, check=True, timeout=240)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            report['cases'].append({'fixture': label, 'passed': True, 'report': str(evidence), 'interactive_output': str(output), 'jobs': jobs})
            (folder / 'printing.json').write_text(json.dumps(report, indent=2))
            print(label, 'PASS', flush=True)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder / 'printing.json').write_text(json.dumps(report, indent=2))
        print(folder / 'printing.json', flush=True)

if __name__ == '__main__':
    main()
