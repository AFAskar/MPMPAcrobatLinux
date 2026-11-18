"""Verified system-window close for one saved disposable Reader document."""
import time


def cancel_reading_preparation(c, path):
    """Cancel only Reader's observed accessibility-preparation task, not PDF work."""
    filename = str(path).replace('\\', '/').rsplit('/', 1)[-1]
    rows = c.command('inspect')
    documents = [w for w in rows if w.get('class') == 'AcrobatSDIWindow' and '.pdf' in w.get('name', '').lower()]
    assert len(documents) == 1 and documents[0]['name'].startswith(filename+' -'), documents
    dialogs = [w for w in rows if w.get('class') in ['#32770', 'AVL_AVDialog']]
    assert len(dialogs) == 1 and dialogs[0]['class'] == '#32770' and dialogs[0]['name'] == 'Preparing document for reading', dialogs
    owner = dialogs[0]['handle']
    buttons = [w for w in rows if w.get('owner') == owner and w.get('class') == 'Button' and w.get('name') == 'Cancel' and w.get('enabled')]
    assert len(buttons) == 1, buttons
    result = {'scope':'Cancel accessibility preparation only; no document calculation, generation or save replay', 'before':rows,
              'invocation':c.command('invoke', name='Cancel', owner=owner)}
    deadline=time.monotonic()+30
    while True:
        after=c.command('inspect')
        if not any(w['handle']==owner for w in after):
            result['after']=after
            return result
        assert time.monotonic()<deadline, after
        time.sleep(0.1)


def close_saved(c, path):
    def normalize(value):
        value = str(value).replace('\\', '/')
        while '//' in value:
            value = value.replace('//', '/')
        return value
    normalized = normalize(path)
    assert normalized.startswith(normalize(c.WIN) + '/runs/') and '..' not in normalized.split('/')
    state = c.ensure_document(path)
    assert len(state.get('openDocuments', [])) == 1, state.get('openDocuments')
    filename = normalized.rsplit('/', 1)[1]
    windows = c.command('inspect')
    documents = [w for w in windows if w.get('class') == 'AcrobatSDIWindow' and '.pdf' in w.get('name', '').lower()]
    assert len(documents) == 1 and documents[0]['name'].startswith(filename + ' -'), documents
    assert not [w for w in windows if w.get('class') == '#32770'], 'A dialog blocks saved-document closure'
    result = {'path': path, 'window': documents[0], 'method': 'observed saved document, Escape and system Alt+F4', 'save_prompts': []}
    result['input'] = c.command('keys', keys='{ESC}%{F4}')
    deadline = time.monotonic() + 40
    while True:
        windows = c.command('inspect')
        save = [w for w in windows if w.get('name', '').startswith('Do you want to save changes') and filename in w['name']]
        for message in save:
            buttons = [w for w in windows if w.get('owner') == message['owner'] and w.get('class') == 'Button' and w.get('name') == 'No' and w.get('enabled')]
            assert len(buttons) == 1, 'Ambiguous post-save confirmation'
            result['save_prompts'].append(c.command('invoke', name='No', owner=message['owner']))
        health = c.command('health')
        if not health.get('readers'):
            result.update(closed=True, process_terminated=True, final_health=health)
            (c.STATE / 'reader-session.json').unlink(missing_ok=True)
            return result
        if time.monotonic() > deadline:
            raise RuntimeError('Reader did not terminate after closing the exact saved document')
        time.sleep(0.1)


def reopen_snapshot(c, path):
    """Copy closed saved bytes exclusively; never rewrite PDF values."""
    assert not c.command('health').get('readers'), 'Require a cold Reader process boundary'
    output = path[:-4] + '-cold-' + str(time.time_ns()) + '.pdf'
    code = '''$sourcePath={source};$targetPath={target}
$sourceStream=[IO.File]::Open($sourcePath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
try {{
 $targetStream=[IO.File]::Open($targetPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try {{$sourceStream.CopyTo($targetStream)}} finally {{$targetStream.Dispose()}}
}} finally {{$sourceStream.Dispose()}}
$sourceHash=(Get-FileHash $sourcePath -Algorithm SHA256).Hash
$targetHash=(Get-FileHash $targetPath -Algorithm SHA256).Hash
if($sourceHash -ne $targetHash){{throw 'Cold reopen snapshot bytes differ'}}
@{{source=$sourcePath;path=$targetPath;source_sha256=$sourceHash;sha256=$targetHash}}|ConvertTo-Json -Compress
'''.format(source=c.literal(path), target=c.literal(output))
    import json
    result = json.loads(c.powershell(code))
    assert result['source_sha256'] == result['sha256']
    return output, result
