#!/usr/bin/env python3
"""Reopen native outputs in qualified real Reader; never modify oracle values with a PDF library."""
import argparse,json,sys,time,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'acrobat'))
import control as c
from verify import inspect,script_hashes

def main():
    stamp=str(time.time_ns());cases=[];report=c.STATE/('native-acrobat-'+stamp+'.json')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--expected',default='""');parser.add_argument('pdfs',nargs='+');args=parser.parse_args()
    expected=json.loads(args.expected) if args.expected!='""' else {'PC Name':'Native Vertical Slice','Str':'18','Str Mod':'4'}
    with c.desktop_lock():
        for arg in args.pdfs:
            local=Path(arg).resolve();remote='runs/native-'+stamp+'-'+local.name
            case={'input':str(local),'remote':remote,'passed':False};cases.append(case)
            try:
                subprocess.run(c.SCP+[str(local),c.SCP_TARGET + ':MPMB-Testing/'+remote],check=True,capture_output=True)
                state=c.script('read',path=c.remote_path(remote),fields=list(expected))
                case['reader']=state
                assert all(str(state['fields'].get(k))==v for k,v in expected.items()),state
                case['independent']=inspect(local,expected)
                assert case['independent']['passed'],case['independent']
                original=next(p for p in (c.REPO/'Testing').glob('*.pdf') if ('Ashnar' in p.name if 'ashnar' in local.name.lower() else ('_2014_' in p.name if '2014' in local.name else '_2024_' in p.name)))
                assert script_hashes(original)==script_hashes(local),'Original embedded scripts changed'
                case['scripts_preserved']=True
                output=remote[:-4]+'-reader-save.pdf'
                c.script('save',path=c.remote_path(remote),output=c.remote_path(output))
                c.script('close',path=c.remote_path(output))
                saved=c.fetch(output,c.STATE/Path(output).name)
                case['reader_saved']=inspect(saved,expected);assert case['reader_saved']['passed']
                assert script_hashes(original)==script_hashes(saved)
                case['passed']=True
            except Exception as e:
                case['error']=str(e)
                try:case['screenshot']=c.command('screenshot')
                except Exception as screenshot_error:case['screenshot_error']=str(screenshot_error)
                break
            finally:report.write_text(json.dumps({'passed':all(x['passed'] for x in cases),'cases':cases},indent=2))
    print(report);return 0 if cases and all(x['passed'] for x in cases) else 1
if __name__=='__main__':raise SystemExit(main())
