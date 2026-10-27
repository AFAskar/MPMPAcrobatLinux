#!/usr/bin/env python3
"""Print original MPMB workflows through guarded Microsoft Print to PDF only.

The virtual printer is checked using both Reader parameters and OCR of the live
printer control. File-picker writes use the scoped native write/read-back bridge.
No physical printer is ever selected or accepted by this suite.
"""
import argparse, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
from PIL import Image, ImageOps
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import inspect, script_hashes


def wait_dialog(title, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        elements = c.command('inspect')
        roots = [e for e in elements if e['name'] == title and e['class'] == '#32770']
        if len(roots) == 1:
            return roots[0], elements
        time.sleep(.1)
    raise RuntimeError('Expected dialog not found: ' + title)


def guard_virtual_printer(folder, label, root):
    elements = c.command('inspect_uia')
    (folder / (label + '-uia.json')).write_text(json.dumps(elements, indent=2))
    # The printer selector is the first ComboBoxEx32 below the print-dialog
    # heading. Bounds are observed anew, never hard-coded screen coordinates.
    combos = sorted([e for e in elements if e['class'] == 'ComboBoxEx32' and e['rect'][2] > 0], key=lambda e: e['rect'][1])
    if not combos:
        raise RuntimeError('Printer selector not inspectable')
    combo = combos[0]
    shot = c.command('screenshot'); local = c.fetch(shot['path'], folder / (label + '-print-dialog.png'))
    x, y, width, height = map(int, combo['rect'])
    image = Image.open(local).crop((x + 2, y + 2, x + width - 15, y + height - 2)).convert('L')
    crop = folder / (label + '-printer-guard.png')
    ImageOps.invert(image).resize((width * 4, height * 4)).save(crop)
    text = subprocess.check_output(['tesseract', str(crop), 'stdout', '--psm', '7'], stderr=subprocess.DEVNULL, text=True).strip()
    if text != 'Microsoft Print to PDF':
        c.command('invoke', name='Cancel', owner=root['handle'])
        raise RuntimeError('Virtual-printer guard rejected selected destination: ' + text)
    return {'name': text, 'control_rect': combo['rect'], 'screenshot': str(local)}



SETTINGS = {'all': 'false!#TheListSeparator#!0', 'selected': 'true!#TheListSeparator#!0,CSfront', 'companion': 'false!#TheListSeparator#!0,AScomp'}

def native_same_state(source, folder, fixture, workflows, binary):
    steps = [{'op': 'advance', 'ms': 4100}]
    for workflow in workflows:
        code = '__host.command(' + json.dumps("Value('Print Remember'," + json.dumps(SETTINGS[workflow]) + ");PrintTheSheet()") + ')'
        steps.append({'op': 'eval', 'code': code})
    spec = {'print_output_dir': str(folder / (fixture + '-native-jobs')), 'dialogs': [{'result': 'ok'}] * 30, 'alerts': [1] * 30, 'steps': steps}
    scenario, evidence = folder / (fixture + '-native-scenario.json'), folder / (fixture + '-native-report.json')
    scenario.write_text(json.dumps(spec))
    with (folder / (fixture + '-native.log')).open('w') as log:
        result = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)], stdout=log, stderr=log, timeout=240)
    data = json.loads(evidence.read_text()); assert result.returncode == 0 and data['passed'], data.get('error')
    jobs = data['diagnostics']['printJobs']; assert len(jobs) == len(workflows)
    return dict(zip(workflows, jobs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_report', type=Path)
    parser.add_argument('--readiness', type=Path, required=True)
    parser.add_argument('--workflow', choices=['all', 'selected', 'companion'], action='append')
    args = parser.parse_args()
    native = json.loads(args.native_report.read_text()); qualification = json.loads(args.readiness.read_text())
    assert native['passed'] and qualification['passed'] and len(qualification['cases']) == 24
    folder = args.native_report.resolve().parent / ('reader-print-output-' + str(time.time_ns())); folder.mkdir()
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'passed': False, 'readiness': str(args.readiness.resolve()), 'cases': [], 'physical_jobs': 0}
    print(folder, flush=True)
    try:
        workflows = args.workflow or ['all', 'selected', 'companion']
        prepared = {case['fixture']: native_same_state(Path(case['interactive_output']), folder, case['fixture'], workflows, binary) for case in native['cases']}
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Reference suite requires no pre-existing document'
            for case in native['cases']:
                fixture = case['fixture']; source = Path(case['interactive_output']); name = 'print-output-' + str(time.time_ns()) + '-' + fixture + '.pdf'; remote = c.remote_path('runs/' + name)
                subprocess.run(c.SCP + [str(source), 'mpmb-test@127.0.0.1:MPMB-Testing/runs/' + name], check=True, capture_output=True)
                c.ensure_document(remote)
                params = c.script('print_params', path=remote)
                assert params.get('printerName', '') in ['', 'Microsoft Print to PDF'], params
                for workflow in workflows:
                    label = fixture + '-' + workflow
                    settings = SETTINGS[workflow]
                    c.script('set', path=remote, values={'Print Remember': settings})
                    ident = c.script_submit('call', path=remote, name='PrintTheSheet', args=[])
                    root, _ = wait_dialog('Print')
                    guard = guard_virtual_printer(folder, label, root)
                    c.command('invoke', name='Print', owner=root['handle'])
                    wait_dialog('Save Print Output As')
                    output = c.remote_path('runs/controlled-print-' + str(time.time_ns()) + '-' + label + '.pdf')
                    picker = c.command('save_print_output', request_id=ident, path=output)
                    assert picker['verified'], picker
                    result = c.script_result(ident)
                    local = c.fetch(output, folder / (label + '-reader-printed.pdf'))
                    printed = PdfReader(local)
                    native_job = prepared[fixture][workflow]
                    native_print = Path(native_job['path'])
                    assert len(printed.pages) == len(PdfReader(native_print).pages), {'reader_pages': len(printed.pages), 'native_pages': len(PdfReader(native_print).pages)}
                    assert not printed.get_fields() and not script_hashes(local)
                    text = subprocess.check_output(['pdftotext', str(local), '-'], text=True)
                    rendered_text = []
                    for page_number in range(1, len(printed.pages) + 1):
                        image = folder / (label + '-reader-page-' + str(page_number))
                        subprocess.run(['pdftoppm', '-f', str(page_number), '-l', str(page_number), '-singlefile', '-scale-to', '1400', '-png', str(local), str(image)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                        # The Windows virtual printer may outline embedded form-font
                        # glyphs. Check every rendered page, including the added companion.
                        rendered_text.append(subprocess.check_output(['tesseract', str(image) + '.png', 'stdout', '--psm', '11'], stderr=subprocess.DEVNULL, text=True))
                    ocr = '\n'.join(rendered_text)
                    (folder / (label + '-rendered-text.txt')).write_text(ocr)
                    visible_text = text + '\n' + ocr
                    normalized = ''.join(visible_text.upper().split())
                    if workflow != 'companion':
                        assert 'PRINTVISIBLE' in normalized and 'PRINTONLY' in normalized, 'Printable sentinel missing from rendered output'
                        assert 'PRINTHIDDEN' not in normalized and 'PRINTSCREENONLY' not in normalized, 'Nonprintable sentinel rendered'
                    else:
                        assert 'WOLF' in normalized
                    report['cases'].append({'fixture': fixture, 'workflow': workflow, 'passed': True, 'virtual_printer': guard, 'picker': picker, 'result': result, 'reader_printed': str(local), 'native_printed': str(native_print), 'form_text_extractable': 'PRINTVISIBLE' in text, 'rendered_text': str(folder / (label + '-rendered-text.txt')), 'pages': len(printed.pages), 'reader_page_sizes': [[float(p.mediabox.width), float(p.mediabox.height)] for p in printed.pages], 'native_page_sizes': [[float(p.mediabox.width), float(p.mediabox.height)] for p in PdfReader(native_print).pages]})
                    (folder / 'print-output.json').write_text(json.dumps(report, indent=2)); print(label, 'virtual print output PASS', flush=True)
                saved = remote[:-4] + '-saved.pdf'; c.script('save', path=remote, output=saved); c.script('close', path=saved)
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        if 'remote' in locals():
            report['failed_document'] = remote
            try:
                with c.desktop_lock():
                    retained = remote[:-4] + '-failure-retained.pdf'
                    c.script('save', path=remote, output=retained); c.script('close', path=retained)
                    report['failure_retained'] = retained
            except Exception as cleanup_error:
                report['cleanup_error'] = str(cleanup_error)
        try:
            shot = c.command('screenshot'); c.fetch(shot['path'], folder / 'failure.png')
        except Exception as screenshot_error:
            report['screenshot_error'] = str(screenshot_error)
        raise
    finally:
        (folder / 'print-output.json').write_text(json.dumps(report, indent=2)); print(folder / 'print-output.json', flush=True)

if __name__ == '__main__':
    main()
