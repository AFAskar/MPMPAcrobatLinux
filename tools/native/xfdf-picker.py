#!/usr/bin/env python3
"""Cancel the genuine owned GTK XFDF picker and verify unchanged saved state.

Uses GDK_DEBUG=no-portals and GTK_A11Y=atspi for an observable GTK backend.
Default KDE portal selection/cancellation and successful file selection remain
unqualified. Run with system Python providing pyatspi; --pdf-python supplies
pypdf for independent saved-field/widget/appearance/script verification.
"""
import argparse, hashlib, json, os, shutil, subprocess, time
from pathlib import Path
import pyatspi
ROOT = Path(__file__).resolve().parents[2]


def descendants(node):
    queue = [node]
    for _ in range(3000):
        if not queue:
            return
        current = queue.pop(0)
        yield current
        queue.extend(list(current))
    raise RuntimeError('Accessibility tree exceeded bound')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf-python', default=str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'))
    args = p.parse_args()
    assert not [a for a in pyatspi.Registry.getDesktop(0) if a.name == 'zenity'], 'Pre-existing zenity application'
    folder = ROOT/'output/testing'/('native-xfdf-picker-cancel-'+str(time.time_ns())); folder.mkdir(); print(folder, flush=True)
    source = next((ROOT/'Testing').glob('*_2024_*.pdf')); binary = folder/'mpmb-reader'; shutil.copy2(ROOT/'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'backend': {'GDK_DEBUG': 'no-portals', 'GTK_A11Y': 'atspi'}}
    expected = {'Player Name': 'Keep Ω', 'Notes.Left': 'Keep **bold** notes'}
    state = "JSON.stringify(['Player Name','Notes.Left'].map(function(name){var f=getField(name);return {name:name,value:f.valueAsString,rich:f.richText?f.richValue:null}}))"
    steps = [{'op':'advance','ms':4100}]+[{'op':'edit','field':k,'value':v} for k,v in expected.items()]+[{'op':'eval','code':'var pickerBefore='+state+';importAnXFDF();if(pickerBefore!=='+state+")throw Error('Picker cancellation changed form state');"},{'op':'assert','values':expected},{'op':'save','path':str(folder/'native.pdf')}]
    scenario = {'interactive':True,'dialogs':[{'title':'SOURCE SELECTION DIALOG','result':'ok'}],'alerts':[1]*10,'steps':steps}
    (folder/'scenario.json').write_text(json.dumps(scenario)); (folder/'expected.json').write_text(json.dumps(expected))
    process = None; owned = None
    try:
        with (folder/'probe.log').open('w') as log:
            process = subprocess.Popen([str(binary),str(source),'--probe',str(folder/'scenario.json'),str(folder/'probe.json')],stdout=log,stderr=log,env={**os.environ,'DISPLAY':':0','XDG_RUNTIME_DIR':'/run/user/1000',**report['backend']})
            deadline = time.monotonic()+60
            while time.monotonic()<deadline:
                assert process.poll() is None, 'Native probe exited before picker'
                apps = [a for a in pyatspi.Registry.getDesktop(0) if a.name=='zenity']
                for app in apps:
                    pid = app.get_process_id()
                    if int(Path('/proc',str(pid),'stat').read_text().split()[3]) != process.pid:
                        continue
                    roots = [n for n in app if n.getRoleName()=='dialog' and n.name=='Import XFDF form data']
                    if not roots:
                        continue
                    assert len(roots)==1; owned=pid; nodes=list(descendants(roots[0]))
                    buttons=[n for n in nodes if n.getRoleName()=='button' and n.name=='Cancel' and n.getState().contains(pyatspi.STATE_SENSITIVE) and n.getState().contains(pyatspi.STATE_SHOWING)]
                    if not buttons:continue
                    assert len(buttons)==1
                    action=buttons[0].queryAction(); offered=[action.getName(i) for i in range(action.nActions)]; assert offered==['click']
                    report['dialog']={'pid':pid,'parent_pid':process.pid,'name':roots[0].name,'tree':[{'role':n.getRoleName(),'name':n.name} for n in nodes]}
                    report['action']={'button':'Cancel','offered':offered,'states':[str(state) for state in buttons[0].getState().getStates()],'result':action.doAction(0)};assert report['action']['result'];break
                if report.get('action'):
                    break
                time.sleep(.2)
            assert report.get('action'), 'Owned GTK picker Cancel did not become ready'
            assert process.wait(timeout=90)==0
        probe=json.loads((folder/'probe.json').read_text());assert probe['passed'],probe.get('error');assert probe['diagnostics']['xfdfImports']==[{'cancelled':True}]
        code="import sys,json;sys.path.insert(0,sys.argv[1]);from verify import inspect,script_hashes;r=inspect(sys.argv[3],json.load(open(sys.argv[4])));assert r['passed'];assert script_hashes(sys.argv[2])==script_hashes(sys.argv[3]);print(json.dumps(r))"
        checked=subprocess.run([args.pdf_python,'-c',code,str(ROOT/'tools/acrobat'),str(source),str(folder/'native.pdf'),str(folder/'expected.json')],capture_output=True,text=True,timeout=90);assert checked.returncode==0,checked.stderr
        report['independent']=json.loads(checked.stdout);assert hashlib.sha256(source.read_bytes()).hexdigest()==report['source_sha256'];report['passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:
        if process and process.poll() is None:
            if owned is not None:
                try: os.kill(owned,15)
                except ProcessLookupError: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.terminate();process.wait(timeout=10)
        (folder/'picker.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'picker.json',flush=True)


if __name__=='__main__':main()
