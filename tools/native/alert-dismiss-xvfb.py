#!/usr/bin/env python3
"""Qualify native alert input on an authenticated isolated X11 display."""
from pathlib import Path
import subprocess,os,time,json,secrets,select,hashlib,argparse,sys,shutil
root=Path(__file__).resolve().parents[2];p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--reader-pdf',type=Path,required=True);p.add_argument('--xvfb',type=Path,default=Path(shutil.which('Xvfb') or root/'output/deps/xvfb/root/usr/bin/Xvfb'));args=p.parse_args();folder=root/'output/testing'/('alert-xvfb-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True)
auth=folder/'authority';auth.touch(mode=0o600);server=args.xvfb.resolve();assert server.is_file(),'Install Xvfb or pass --xvfb';display=next(n for n in range(93,190) if not Path('/tmp/.X11-unix/X'+str(n)).exists() and not Path('/tmp/.X'+str(n)+'-lock').exists());subprocess.run(['xauth','-f',str(auth),'add',':'+str(display),'MIT-MAGIC-COOKIE-1',secrets.token_hex(16)],check=True,capture_output=True)
read,write=os.pipe();report={'passed':False,'scope':'Isolated authenticated native X11 display, actual UI input; no KDE/Wayland focus or pixel-equivalence qualification','display':display,'xvfb_sha256':hashlib.sha256(server.read_bytes()).hexdigest()}
with (folder/'xvfb.log').open('w') as log:
 p=subprocess.Popen([str(server),':'+str(display),'-displayfd',str(write),'-screen','0','1280x900x24','-nolisten','tcp','-noreset','-auth',str(auth)],pass_fds=[write],stdout=log,stderr=log);os.close(write)
 try:
  assert select.select([read],[],[],15)[0],'Xvfb startup deadline';assert os.read(read,100).decode().strip()==str(display);os.close(read)
  env=dict(os.environ,DISPLAY=':'+str(display),XAUTHORITY=str(auth),MPMB_HEADLESS_X11='1',LIBGL_ALWAYS_SOFTWARE='1');env.pop('WAYLAND_DISPLAY',None)
  with (folder/'native.log').open('w') as native:
   run=subprocess.run([os.environ.get('MPMB_PYTHON',sys.executable),'tools/native/alert-dismiss-desktop.py','--reader',str(args.reader.resolve()),'--reader-pdf',str(args.reader_pdf.resolve())],cwd=root,env=env,stdout=native,stderr=native,timeout=600)
  report['returncode']=run.returncode;assert run.returncode==0
  result=Path((folder/'native.log').read_text().splitlines()[-1]);report['native_report']=str(result);data=json.loads(result.read_text());assert data['passed'];report['passed']=True
 except Exception as e:report['error']=str(e);raise
 finally:
  p.terminate();p.wait(timeout=10);auth.unlink(missing_ok=True);(folder/'qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'qualification.json',flush=True)
