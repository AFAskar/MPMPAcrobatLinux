#!/usr/bin/env python3
"""Real native alert Escape/window-close comparison with a qualified Reader report.

Runs original RunUserScript after a cold load of the initialized Reader save, matching the reference
entry points. X11 controls only exact observed child windows owned by this probe.
This host-dialog contract does not qualify class choices or generic execDialog.
"""
from pathlib import Path
import ctypes as C,ctypes.util,json,os,subprocess,time,hashlib
ROOT=Path(__file__).resolve().parents[2]
x=C.CDLL(ctypes.util.find_library('X11'));U=C.c_ulong;I=C.c_int;P=C.c_void_p
x.XOpenDisplay.argtypes=[C.c_char_p];x.XOpenDisplay.restype=P
x.XDefaultRootWindow.argtypes=[P];x.XDefaultRootWindow.restype=U
x.XInternAtom.argtypes=[P,C.c_char_p,I];x.XInternAtom.restype=U
x.XQueryTree.argtypes=[P,U,C.POINTER(U),C.POINTER(U),C.POINTER(C.POINTER(U)),C.POINTER(C.c_uint)];x.XQueryTree.restype=I
x.XFetchName.argtypes=[P,U,C.POINTER(C.c_char_p)];x.XFetchName.restype=I
x.XFree.argtypes=[P];x.XFree.restype=I
x.XGetWindowProperty.argtypes=[P,U,U,C.c_long,C.c_long,I,U,C.POINTER(U),C.POINTER(I),C.POINTER(U),C.POINTER(U),C.POINTER(C.POINTER(C.c_ubyte))];x.XGetWindowProperty.restype=I
x.XFlush.argtypes=[P];x.XFlush.restype=I
class Data(C.Union):_fields_=[('l',C.c_long*5)]
class Client(C.Structure):_fields_=[('type',I),('serial',U),('send_event',I),('display',P),('window',U),('message_type',U),('format',I),('data',Data)]
class Event(C.Union):_fields_=[('xclient',Client),('pad',C.c_long*24)]
x.XSendEvent.argtypes=[P,U,I,C.c_long,C.POINTER(Event)];x.XSendEvent.restype=I
D=x.XOpenDisplay(None);assert D,'X11 display unavailable';root=x.XDefaultRootWindow(D)
def atom(n):return x.XInternAtom(D,n.encode(),False)
def prop(w,name):
 typ=U();fmt=I();count=U();after=U();data=C.POINTER(C.c_ubyte)();status=x.XGetWindowProperty(D,w,atom(name),0,4096,False,0,C.byref(typ),C.byref(fmt),C.byref(count),C.byref(after),C.byref(data));assert status==0
 try:return list(C.cast(data,C.POINTER(U))[:count.value]) if data and fmt.value==32 else []
 finally:
  if data:x.XFree(data)
def windows(w,depth=0):
 a=U();b=U();children=C.POINTER(U)();count=C.c_uint()
 if not x.XQueryTree(D,w,C.byref(a),C.byref(b),C.byref(children),C.byref(count)):return
 try:items=list(children[:count.value])
 finally:
  if children:x.XFree(children)
 for child in items:
  name=C.c_char_p();x.XFetchName(D,child,C.byref(name))
  try:title=name.value.decode('utf8','replace') if name.value else ''
  finally:
   if name:x.XFree(name)
  if title:yield child,title
  if depth<3:yield from windows(child,depth+1)

import argparse,importlib.util,signal
sys=__import__('sys');sys.path.insert(0,str(ROOT/'tools/acrobat'))
from verify import script_hashes

def module(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/'tools/native'/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

xt=C.CDLL(ctypes.util.find_library('Xtst'));xt.XTestFakeKeyEvent.argtypes=[P,C.c_uint,I,U];xt.XTestFakeKeyEvent.restype=I
x.XKeysymToKeycode.argtypes=[P,U];x.XKeysymToKeycode.restype=C.c_ubyte
x.XSetInputFocus.argtypes=[P,U,I,U];x.XSetInputFocus.restype=I
x.XSync.argtypes=[P,I];x.XSync.restype=I
x.XGetInputFocus.argtypes=[P,C.POINTER(U),C.POINTER(I)];x.XGetInputFocus.restype=I
handler=C.CFUNCTYPE(I,P,P)(lambda display,error:0);x.XSetErrorHandler.argtypes=[P];x.XSetErrorHandler.restype=P;x.XSetErrorHandler(handler)

class Attributes(C.Structure):
 _fields_=[('x',I),('y',I),('width',I),('height',I),('border_width',I),('depth',I),('visual',P),('root',U),('window_class',I),('bit_gravity',I),('win_gravity',I),('backing_store',I),('backing_planes',U),('backing_pixel',U),('save_under',I),('colormap',U),('map_installed',I),('map_state',I),('all_event_masks',C.c_long),('your_event_mask',C.c_long),('do_not_propagate_mask',C.c_long),('override_redirect',I),('screen',P)]
x.XGetWindowAttributes.argtypes=[P,U,C.POINTER(Attributes)];x.XGetWindowAttributes.restype=I

def activate(w):
 deadline=time.monotonic()+10;attributes=Attributes()
 while not x.XGetWindowAttributes(D,w,C.byref(attributes)) or attributes.map_state!=2:
  assert time.monotonic()<deadline,'Native window not viewable';time.sleep(.1)
 if prop(root,'_NET_SUPPORTING_WM_CHECK'):
  event=Event();event.xclient.type=33;event.xclient.send_event=True;event.xclient.display=D;event.xclient.window=w;event.xclient.message_type=atom('_NET_ACTIVE_WINDOW');event.xclient.format=32;event.xclient.data.l[0]=2;event.xclient.data.l[1]=0
  assert x.XSendEvent(D,root,False,(1<<19)|(1<<20),C.byref(event));x.XSync(D,False)
  while prop(root,'_NET_ACTIVE_WINDOW')!=[w]:
   assert time.monotonic()<deadline,'Exact native alert did not become the active window';time.sleep(.1)
 else:assert os.environ.get('MPMB_HEADLESS_X11')=='1','Require explicit isolated-display mode without a window manager'
 x.XSetInputFocus(D,w,2,0);x.XSync(D,False)
 focused=U();revert=I()
 while True:
  x.XGetInputFocus(D,C.byref(focused),C.byref(revert))
  if focused.value==w:break
  assert time.monotonic()<deadline,('Native alert focus differs',w,focused.value,prop(root,'_NET_ACTIVE_WINDOW'));time.sleep(.1)

def key(w,symbol):
 activate(w);code=x.XKeysymToKeycode(D,symbol);assert code
 assert xt.XTestFakeKeyEvent(D,code,True,0);assert xt.XTestFakeKeyEvent(D,code,False,0);x.XSync(D,False)

def close(w):
 delete=atom('WM_DELETE_WINDOW');assert delete in prop(w,'WM_PROTOCOLS')
 event=Event();event.xclient.type=33;event.xclient.send_event=True;event.xclient.display=D;event.xclient.window=w;event.xclient.message_type=atom('WM_PROTOCOLS');event.xclient.format=32;event.xclient.data.l[0]=delete;event.xclient.data.l[1]=0
 assert x.XSendEvent(D,w,False,0,C.byref(event));x.XSync(D,False)

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reader',type=Path,required=True);p.add_argument('--reader-pdf',type=Path,required=True);args=p.parse_args()
reader=json.loads(args.reader.read_text());assert reader['passed'] and len(reader['cases'])==8
assert [(c['type'],c['method']) for c in reader['cases']]==[(k,m) for k in range(4) for m in ['escape','window-close']]
fixture=next((ROOT/'Testing').glob('*_2024_*.pdf'));assert hashlib.sha256(fixture.read_bytes()).hexdigest()==reader['input_sha256'];source=args.reader_pdf.resolve();before=hashlib.sha256(source.read_bytes()).hexdigest()
style=module('style','default-style-persistence.py');profile=module('profile','fighter-styles.py');expected=style.saved_capture(args.reader_pdf,reader['summary'],fixture);assert expected==reader['captured']
folder=ROOT/'output/testing'/('native-alert-dismiss-'+str(time.time_ns()));folder.mkdir();print(folder,flush=True);binary=folder/'mpmb-reader';__import__('shutil').copy2(ROOT/'target/debug/mpmb-reader',binary)
steps=[{'op':'advance','ms':4100}];scripts=[]

for case in reader['cases']:
 script=("var iFileName='Alert dismissal diagnostic.js';var result=app.alert({cMsg:'Controlled dismissal test',cTitle:%s,nType:%d});"%(json.dumps(case['title']),case['type']))+r"""if(!tDoc.__alertDismissResults)tDoc.__alertDismissResults=[];tDoc.__alertDismissResults.push({type:__TYPE__,method:__METHOD__,button:result});Value('PC Name',JSON.stringify({results:tDoc.__alertDismissResults,sentinel:'\u00a0\u2028\ud83d\ude00'}).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));""".replace('__TYPE__',str(case['type'])).replace('__METHOD__',json.dumps(case['method']))
 scripts.append(script);steps.append({'op':'eval','code':"Value('User Script',"+json.dumps(script)+");__host.command('RunUserScript(false)')"})
steps.append({'op':'eval','code':"Value('User Script','')"});summary_index=len(steps);steps.append({'op':'eval','code':profile.SUMMARY});output=folder/'native.pdf';steps.append({'op':'save','path':str(output)});scenario=folder/'scenario.json';scenario.write_text(json.dumps({'interactive':True,'steps':steps}));(folder/'observers.json').write_text(json.dumps(scripts,indent=2))
report={'passed':False,'scope':__doc__,'reader':str(args.reader.resolve()),'reader_pdf':str(args.reader_pdf.resolve()),'input':str(source),'input_sha256':before,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':[]}
env=dict(os.environ);env.pop('WAYLAND_DISPLAY',None)
with (folder/'run.log').open('w') as log:
 process=subprocess.Popen([str(binary),str(source),'--probe',str(scenario),str(folder/'probe.json')],stdout=log,stderr=log,env=env,start_new_session=True)
 try:
  for reference in reader['cases']:
   deadline=time.monotonic()+90
   while True:
    found=[(w,t) for w,t in windows(root) if t==reference['title']]
    if found:break
    report['last_visible_titles']=[t for _,t in windows(root)];assert process.poll() is None,'Native probe exited before alert';assert time.monotonic()<deadline,'Exact alert not observed';time.sleep(.1)
   assert len(found)==1;w,title=found[0];pids=prop(w,'_NET_WM_PID');assert len(pids)==1;pid=pids[0];status=Path('/proc/'+str(pid)+'/status').read_text();parent=int(next(line.split()[1] for line in status.splitlines() if line.startswith('PPid:')));assert parent==process.pid
   case={'type':reference['type'],'method':reference['method'],'observed':{'window':w,'title':title,'dialog_pid':pid,'parent_pid':parent}};report['cases'].append(case);activate(w);time.sleep(.3)
   if reference['method']=='escape':key(w,0xff1b)
   else:close(w)
   time.sleep(.8);case['dismissed']=not Path('/proc/'+str(pid)).exists();assert case['dismissed']==reference['dismissed'],case
   if not case['dismissed']:
    # No edits/checkboxes exist in these descriptors. Tab starts at the first
    # button: OK, or Yes then No. The returned API code independently verifies
    # the fallback selection; it is not injected as a scripted alert response.
    count=1 if reference['type']==0 else 2
    for _ in range(count):key(w,0xff09);time.sleep(.1)
    key(w,0xff0d);case['fallback']='Tab to actual OK/No button and Enter'
   deadline=time.monotonic()+12
   while Path('/proc/'+str(pid)).exists():
    assert time.monotonic()<deadline,'Native dialog did not complete after actual input';time.sleep(.1)
   (folder/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
  assert process.wait(timeout=90)==0
  data=json.loads((folder/'probe.json').read_text());assert data['passed'] and not data['diagnostics']['errors'] and not data['diagnostics']['console']['messages'],data.get('error');captured=style.saved_capture(output,data['stages'][summary_index]['result'],source);report['captured']=captured;assert captured==expected,(captured,expected);assert script_hashes(output)==script_hashes(source) and hashlib.sha256(source.read_bytes()).hexdigest()==before;report.update(passed=True,pdf=str(output))
 except Exception as e:report['error']=str(e);raise
 finally:
  if process.poll() is None:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=15);report['terminated_disposable_test_group']=True
  (folder/'control.json').write_text(json.dumps(report,indent=2)+'\n');print(folder/'control.json',flush=True)
