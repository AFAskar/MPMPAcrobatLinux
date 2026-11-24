#!/usr/bin/env python3
"""Observe Reader console output, clear/show and return values in one document.

Use original RunUserScript in menu context; inspect the actual owned debugger
edit, close only that observed window, save ASCII diagnostic carriers and verify
their checksums/scripts independently. This is console API/UI qualification,
not an original character workflow or interactive-console-input pass.
"""
import argparse,hashlib,importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/acrobat'))
import control as c
spec=importlib.util.spec_from_file_location('style',ROOT/'tools/native/default-style-persistence.py');style=importlib.util.module_from_spec(spec);spec.loader.exec_module(style)
MESSAGE='MPMB console reference sentinel'


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def observed_console(expected):
    rows=c.command('inspect');roots=[r for r in rows if r.get('class')=='#32770' and r.get('name')=='JavaScript Debugger'];_require(len(roots)==1,'Expected one observed console window')
    owner=roots[0]['handle'];edits=[r for r in rows if r.get('owner')==owner and r.get('class')=='RICHEDIT50W'];_require(len(edits)==1,'Expected one observed console edit')
    observed=read_console_text(owner,edits[0]['handle'])
    _require(observed['live']['text'].rstrip('\r\n')==expected,observed)
    observed['rows']=rows
    return observed


class ConsoleReadError(RuntimeError):
    def __init__(self, message, attempts):
        self.read_attempts = attempts
        super().__init__(message)


def read_console_text(owner, edit, *, controller=None, max_attempts=3):
    """Retry only bounded live text reads; never replay input or PDF commands.

    Each attempt re-observes the exact owned debugger/edit. All getter failures
    are retained even if a later read succeeds. No cached caption fallback.
    """
    controller = c if controller is None else controller
    if not owner or not edit or not 1 <= max_attempts <= 3:
        raise ValueError('Observed handles and one to three read attempts required')
    attempts = []
    for index in range(max_attempts):
        rows = controller.command('inspect')
        roots = [r for r in rows if r.get('handle') == owner and r.get('class') == '#32770'
                 and r.get('name') == 'JavaScript Debugger' and r.get('enabled')]
        edits = [r for r in rows if r.get('handle') == edit and r.get('owner') == owner
                 and r.get('class') == 'RICHEDIT50W' and r.get('enabled')
                 and len(r.get('rect', [])) == 4 and r['rect'][2] > 0 and r['rect'][3] > 0]
        observation = {'attempt': index + 1, 'owner': owner, 'handle': edit,
                       'ownership_valid': len(roots) == len(edits) == 1}
        if not observation['ownership_valid']:
            attempts.append(observation)
            raise ConsoleReadError('Observed debugger/edit ownership changed', attempts)
        observation['inspection_text_error'] = edits[0].get('text_error')
        try:
            live = controller.command('dialog_control', owner=owner, handle=edit)
            if (live.get('owner') != owner or live.get('handle') != edit
                    or live.get('class') != 'RICHEDIT50W' or not isinstance(live.get('text'), str)):
                raise RuntimeError('Live console reply identity/text differs')
        except RuntimeError as error:
            observation['error'] = str(error)
            attempts.append(observation)
            transient = ('ControlText' in str(error) and any(marker in str(error) for marker in
                         ['Control query timed out', 'Control text read timed out']))
            if not transient or index + 1 == max_attempts:
                raise ConsoleReadError(str(error), attempts) from error
            continue
        observation['succeeded'] = True
        attempts.append(observation)
        return {'owner': owner, 'edit': edit, 'live': live, 'read_attempts': attempts}
    raise AssertionError('Unreachable console read state')


def close_console(observed):
    focused=c.command('focus_control',owner=observed['owner'],handle=observed['edit']);_require(focused['focused'],'Console focus failed')
    result=c.command('keys',keys='%{F4}');_require(not [r for r in c.command('inspect') if r.get('class')=='#32770' and r.get('name')=='JavaScript Debugger'],'Console did not close')
    return {'focus':focused,'action':result}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--readiness',type=Path,required=True);args=p.parse_args();ready=json.loads(args.readiness.read_text());assert ready['passed'] and len(ready['cases'])==24 and ready['harness_sha256']==c.harness_fingerprint()
    source=next((ROOT/'Testing').glob('*_2014_*.pdf'));folder=ROOT/'output/testing'/('reader-console-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
    remote=c.remote_path('runs/console-'+str(time.time_ns())+'.pdf');report={'passed':False,'scope':__doc__,'readiness':str(args.readiness.resolve()),'cases':[]};opened=False;pending=None;active_console=None
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP+[str(source),'mpmb-test@127.0.0.1:MPMB-Testing/runs/'+remote.replace('\\','/').split('/')[-1]],check=True,capture_output=True);opened=True;c.ensure_document(remote)
            for phase,expected in [('printed',MESSAGE),('cleared','')]:
                case_folder=folder/phase;case_folder.mkdir()
                body="r.clear_return=typeof console.clear();"+("r.println_return_value=console.println("+json.dumps(MESSAGE)+");r.println_return=typeof r.println_return_value;" if phase=='printed' else '')+"r.show_return=typeof console.show();"
                observer=r"""var iFileName='Reader console observation.js';Value('User Script','');(function(d){var r={phase:__PHASE__,sentinel:'\u00a0\u2028\ud83d\ude00'};__BODY__Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);""".replace('__PHASE__',json.dumps(phase)).replace('__BODY__',body)
                observer_path=case_folder/'observer.js';observer_path.write_text(observer)
                case={'passed':False,'scope':__doc__,'input':str(source.resolve()),'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'observer':str(observer_path.resolve()),'observer_sha256':hashlib.sha256(observer.encode()).hexdigest(),'phase':phase,'readiness':str(args.readiness.resolve())};report['cases'].append(case)
                c.script('set',path=remote,values={'User Script':observer});pending=c.script_submit('call',path=remote,name='RunUserScript',args=[False]);case['request']=pending;case['completion']=c.script_result(pending,timeout=120);pending=None
                active_console=observed_console(expected);case['console']=active_console;case['console_close']=close_console(active_console);active_console=None
                summary=c.script('field_summary',path=remote,fields=['PC Name'])['fields']['PC Name'];case['summary']=summary;saved=remote[:-4]+'-'+phase+'.pdf';c.script('save',path=remote,output=saved);remote=saved;local=c.fetch(remote,case_folder/'reader.pdf');case['captured']=style.saved_capture(local,summary,source)
                assert case['captured']['clear_return']==case['captured']['show_return']=='undefined';assert phase!='printed' or isinstance(case['captured']['println_return_value'],bool);case['passed']=True;(case_folder/'observation.json').write_text(json.dumps(case,indent=2)+'\n');(folder/'console.json').write_text(json.dumps(report,indent=2)+'\n')
            report['close']=c.script('close',path=remote);opened=False;report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    shot=c.command('screenshot');c.fetch(shot['path'],folder/'failure.png')
                    if pending:report['original_completion']=c.script_result(pending,timeout=90)
                    if active_console:report['cleanup_console_close']=close_console(active_console)
                    retained=remote[:-4]+'-failed-retained.pdf';c.script('save',path=remote,output=retained);report['cleanup_close']=c.script('close',path=retained);c.fetch(retained,folder/'failed-retained.pdf')
            except Exception as error:report['cleanup_error']=str(error)
        (folder/'console.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'console.json',flush=True)


if __name__=='__main__':main()
