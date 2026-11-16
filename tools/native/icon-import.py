#!/usr/bin/env python3
"""Bounded native button-media persistence, using synthetic private media.

Explicit-path API diagnostics only: original menu/file-picker and Reader
interoperability require separate qualification. Never edits the supplied PDF.
"""
import argparse, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/acrobat'))
sys.path.insert(0, str(ROOT/'tools/native'))
from verify import canonical_fields, script_hashes
import subclass_audit_qualification as qualification


def media(path):
    r = PdfReader(path)
    widgets = []
    for page in r.pages:
        for ref in page.get('/Annots', []):
            w = ref.get_object()
            chain = [w]
            while chain[-1].get('/Parent'):
                chain.append(chain[-1]['/Parent'].get_object())
            name = '.'.join(str(n['/T']) for n in reversed(chain) if n.get('/T'))
            if name != 'Portrait':
                continue
            icon = w['/MK']['/I'].get_object()
            ap = w['/AP']['/N'].get_object()
            assert b'/Icon Do' in ap.get_data()
            assert ap['/Resources']['/XObject']['/Icon'].get_object().get_data() == icon.get_data()
            images = []
            annotations = []
            for name, obj in icon.get('/Resources', {}).get('/XObject', {}).items():
                obj = obj.get_object()
                if str(name).startswith('/MPMBIconAnnotation'):
                    annotations.append({'name': str(name), 'content': obj.get_data().decode('ascii')})
                if obj.get('/Subtype') == '/Image':
                    images.append({'rgb': obj.get_data().hex(), 'width': int(obj['/Width']), 'height': int(obj['/Height']), 'alpha': obj['/SMask'].get_object().get_data().hex() if '/SMask' in obj else None})
            widgets.append({'content': icon.get_data().decode('ascii'), 'matrix': list(icon.get('/Matrix', [1, 0, 0, 1, 0, 0])), 'images': images, 'annotations': annotations})
    assert widgets, 'No projected portrait widgets'
    return widgets


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--binary', type=Path, required=True)
    a = p.parse_args()
    folder = ROOT/'output/testing'/('native-icon-import-'+str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    source = a.input.resolve()
    binary = folder/'mpmb-reader'
    shutil.copy2(a.binary.resolve(), binary)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = {'passed': False, 'scope': __doc__, 'input': str(source), 'input_sha256': sha(source), 'binary_sha256': sha(binary), 'phases': []}
    original = canonical_fields(PdfReader(source))
    png = folder/'alpha.png'
    Image.frombytes('RGBA', (2, 1), bytes([255, 0, 0, 255, 0, 255, 0, 128])).save(png)
    pdf = folder/'pages.pdf'
    writer = PdfWriter()
    for rotate, content in [(0, b'1 0 0 rg 0 0 40 20 re f'), (90, b'0 0 1 rg 0 0 40 20 re f')]:
        page = writer.add_blank_page(40, 20)
        stream = DecodedStreamObject()
        stream.set_data(content)
        page[NameObject('/Contents')] = writer._add_object(stream)
        page[NameObject('/Resources')] = DictionaryObject()
        page[NameObject('/Rotate')] = NumberObject(rotate)
    writer.write(pdf)

    def run(label, source, code):
        output = folder/(label+'.pdf')
        scenario = folder/(label+'-scenario.json')
        evidence = folder/(label+'-probe.json')
        scenario.write_text(json.dumps({'steps': [{'op': 'advance', 'ms': 5100}, {'op': 'eval', 'code': code}, {'op': 'save', 'path': str(output)}], 'dialogs': []}))
        with (folder/(label+'.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)], stdout=log, stderr=log, timeout=240)
        data = json.loads(evidence.read_text())
        q = qualification.qualify_probe(proc.returncode, data)
        assert q['passed'], q
        assert script_hashes(output) == script_hashes(a.input)
        assert canonical_fields(PdfReader(output)) == original, 'Media-only edit changed canonical field state'
        result = media(output)
        report['phases'].append({'label': label, 'pdf': str(output), 'media': result, 'probe': str(evidence), 'qualification': q, 'imports': data['diagnostics']['iconImports']})
        (folder/'progress.json').write_text(json.dumps(report, indent=2))
        return output, result

    try:
        first, image = run('png', source, 'if(getField("Portrait").buttonImportIcon('+json.dumps(str(png))+')!==0)throw Error("PNG import failed")')
        assert all(v['images'] == [{'rgb': 'ff000000ff00', 'width': 2, 'height': 1, 'alpha': 'ff80'}] for v in image)
        png.unlink()
        cold, retained = run('cold-png', first, 'getField("Portrait").buttonSetIcon(getField("Portrait").buttonGetIcon());')
        assert retained == image
        failed, retained = run('missing-path', cold, 'if(getField("Portrait").buttonImportIcon('+json.dumps(str(png))+')!==-1)throw Error("Missing-path code")')
        assert retained == image
        selected, vector = run('pdf-page-two', failed, 'if(getField("Portrait").buttonImportIcon('+json.dumps(str(pdf))+',1)!==0)throw Error("PDF page import failed")')
        assert all(v['matrix'] == [0, -1, 1, 0, 0, 0] and v['content'].strip() == '0 0 1 rg 0 0 40 20 re f' and not v['images'] for v in vector)
        pdf.unlink()
        invalid, retained = run('invalid-page', selected, 'if(getField("Portrait").buttonImportIcon('+json.dumps(str(first))+',9999)!==-2)throw Error("Invalid-page code")')
        assert retained == vector
        final, retained = run('cold-vector', invalid, 'getField("Portrait").buttonSetIcon(getField("Portrait").buttonGetIcon());')
        assert retained == vector
        # An existing printable widget normal AP is part of Reader's selected
        # PDF-page icon. Copy that visual content, never interactive field actions.
        annotated = folder/'annotated.pdf'
        writer = PdfWriter()
        page = writer.add_blank_page(160, 200)
        page[NameObject('/Rotate')] = NumberObject(90)
        background = DecodedStreamObject()
        background.set_data(b'0 1 0 rg 0 0 160 200 re f\n')
        page[NameObject('/Contents')] = writer._add_object(background)
        page[NameObject('/Resources')] = DictionaryObject()
        ap = DecodedStreamObject()
        ap.set_data(b'1 1 1 rg 0 0 120 40 re f 0 0 0 rg 10 10 100 20 re f\n')
        ap.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Form'),
                   NameObject('/BBox'): ArrayObject([NumberObject(v) for v in [0,0,120,40]]),
                   NameObject('/Resources'): DictionaryObject()})
        widget = writer._add_object(DictionaryObject({NameObject('/Subtype'): NameObject('/Widget'),
            NameObject('/FT'): NameObject('/Tx'), NameObject('/F'): NumberObject(4),
            NameObject('/Rect'): ArrayObject([NumberObject(v) for v in [20,80,140,120]]),
            NameObject('/AP'): DictionaryObject({NameObject('/N'): writer._add_object(ap)})}))
        page[NameObject('/Annots')] = ArrayObject([widget])
        writer.write(annotated)
        imported, visual = run('pdf-widget', final, 'if(getField("Portrait").buttonImportIcon('+json.dumps(str(annotated))+',0)!==0)throw Error("Widget page import failed")')
        assert all(len(v['annotations']) == 1 and '100 20 re f' in v['annotations'][0]['content'] for v in visual)
        annotated.unlink()
        final, retained = run('cold-widget', imported, 'getField("Portrait").buttonSetIcon(getField("Portrait").buttonGetIcon());')
        assert retained == visual
        assert sha(source) == report['input_sha256']
        report.update(passed=True, pdf=str(final))
    except Exception as e:
        report['error'] = str(e)
        raise
    finally:
        (folder/'imports.json').write_text(json.dumps(report, indent=2)+'\n')
        print(folder/'imports.json', flush=True)


if __name__ == '__main__':
    main()
