"""Matched document-timer observation without re-importing add-ons per sample.

Both engines install through the original RunUserScript once per runtime.
Requests use a harmless comment in the diagnostic User Script field; a timer in
that document executes the observer and acknowledges its actual invocation count.
No bridge allowlist or original MPMB function is replaced. Clear the field before
saving. The timer/callback are runtime-only and must be reinstalled after reopen.
"""
import time
MODE = 'installed-once-timer'
FIELD = 'User Script'
REQUEST = '// MPMB additional capture request'
DONE = '// MPMB additional capture complete:'
FAILED = '// MPMB additional capture failed:'


def install(setup, observer):
    return setup + ';tDoc.__fighterAdditionalCaptureCount=0;' + '\n' + (
        'tDoc.__fighterAdditionalCapture=function(){' + observer + '};\n'
        'tDoc.__fighterAdditionalTick=function(){\n'
        ' if(tDoc.getField("User Script").valueAsString===' + repr(REQUEST) + '){\n'
        '  try{tDoc.__fighterAdditionalCapture();tDoc.__fighterAdditionalCaptureCount++;'
        'tDoc.getField("User Script").value=' + repr(DONE) + '+tDoc.__fighterAdditionalCaptureCount;}\n'
        '  catch(e){tDoc.getField("User Script").value=' + repr(FAILED) + '+String(e);}\n'
        ' }\n'
        ' tDoc.__fighterAdditionalTimer=app.setTimeOut("tDoc.__fighterAdditionalTick()",250);\n'
        '};tDoc.__fighterAdditionalTimer=app.setTimeOut("tDoc.__fighterAdditionalTick()",250);'
    )


def native_request():
    return ('Value("User Script",' + repr(REQUEST) + ');__host.advance(1000);'
            'if(What("User Script").indexOf(' + repr(DONE) + ')!==0)'
            'throw Error("Diagnostic timer did not complete: "+What("User Script"));'
            'What("User Script")')


def reader_request(c, path):
    c.script('set', path=path, values={FIELD: REQUEST})
    deadline = time.monotonic() + 30
    while True:
        marker = c.script('read', path=path, fields=[FIELD])['fields'][FIELD]
        if marker.startswith(DONE):
            count = int(marker[len(DONE):])
            assert count > 0
            return {'marker': marker, 'invocation_count': count}
        if marker.startswith(FAILED) or time.monotonic() >= deadline:
            raise RuntimeError('Diagnostic timer did not complete: ' + marker)
        time.sleep(0.1)
