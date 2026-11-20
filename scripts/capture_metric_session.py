"""Bounded raw Metric research capture plus startup checkpoint, not a quote recorder."""
import argparse,collections,json,os,selectors,shutil,struct,subprocess,time,signal
from pathlib import Path
from tape import MAGIC,decode,MAX_FRAME,write_record
from checkpoint_recovery import RecoveryRunner

def main():
 ap=argparse.ArgumentParser();ap.add_argument('directory');ap.add_argument('--seconds',type=int,default=7200);ap.add_argument('--capture-config',default='config/push.json');ap.add_argument('--recovery-config',default='config/checkpoint-recovery.json');a=ap.parse_args()
 options=json.loads(Path(a.recovery_config).read_text())
 for key in ('max_buffer_blocks','max_attempts','retry_seconds','retry_max_seconds','bootstrap_timeout_seconds','alignment_timeout_seconds'):
  if not isinstance(options[key],int) or options[key]<=0:raise ValueError('invalid recovery option: '+key)
 if options.get('backend','trace') not in ('trace','known_slots'):raise ValueError('unknown checkpoint backend')
 if options.get('backend')=='known_slots'and not Path(options['template']).is_file():raise ValueError('missing checkpoint template')
 if a.seconds<=0:raise ValueError('duration must be positive')
 directory=Path(a.directory);directory.mkdir(parents=True,exist_ok=False)
 cfg=json.loads(Path(a.capture_config).read_text());cfg['pools']=[p for p in cfg['pools'] if p.get('curator')=='Carcosa' or p.get('record_enabled') is True];cfg['feed_url']='ws://127.0.0.1:19659';cfg['duration_secs']=a.seconds
 cfg['checkpoint_recovery']=options
 config=directory/'capture.json';config.write_text(json.dumps(cfg,indent=2)+'\n');started=time.time();children=[];handles=[];counts=collections.Counter();symbols=collections.Counter();last={};error=None
 def save(finished=False):
  status=dict(pid=os.getpid(),started_ns=int(started*1e9),deadline_ns=int((started+a.seconds)*1e9),updated_ns=time.time_ns(),finished=finished,counts=dict(counts),symbols=dict(symbols),last_source_ns=last,quote_pipeline='not_connected',checkpoint_status=None if recovery.job is None else recovery.job['process'].poll(),recovery=recovery.status(),error=error,children={name:p.pid for name,p in children},exit_codes={name:p.poll() for name,p in children})
  tmp=directory/'status.tmp';tmp.write_text(json.dumps(status,indent=2)+'\n');tmp.replace(directory/'status.json')
  tmp=directory/'checkpoint-recovery.tmp';tmp.write_text(json.dumps(recovery.status(),indent=2)+'\n');tmp.replace(directory/'checkpoint-recovery.json')
 capture=None;compressor=None
 def emit_marker(row):
  if compressor is not None:write_record(compressor.stdin,row)
 recovery=RecoveryRunner(directory,config,options,emit_marker,children)
 stop_requested=False
 def stop(signum,frame):
  nonlocal stop_requested
  stop_requested=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 try:
  relaylog=open(directory/'relay.log','wb');handles.append(relaylog)
  relay=subprocess.Popen([options.get('relay_python','/tmp/push-ws-env/bin/python'),'examples/push_ws_relay.py','19659','--timestamp'],stdout=relaylog,stderr=relaylog);children.append(('relay',relay))
  time.sleep(1)
  if relay.poll() is not None:raise RuntimeError('relay failed to start')
  err=open(directory/'capture.log','wb');handles.append(err)
  capture=subprocess.Popen(['target/release/examples/push_capture',str(config),str(a.seconds)],stdout=subprocess.PIPE,stderr=err);children.append(('capture',capture))
  compressed=open(directory/'raw.bin.zst','xb');handles.append(compressed)
  compressor=subprocess.Popen(['zstd','-q','-T1','-c'],stdin=subprocess.PIPE,stdout=compressed);children.append(('compressor',compressor))
  sel=selectors.DefaultSelector();sel.register(capture.stdout,selectors.EVENT_READ);buffer=bytearray();header=False;last_save=0
  while not stop_requested and time.time()<started+a.seconds+30:
   if time.time()-last_save>=5:
    save();last_save=time.time()
    if shutil.disk_usage(directory).free<options.get('disk_reserve_gib',5)*1024**3:raise RuntimeError('disk reserve reached')
   recovery.poll()
   ready=sel.select(1)
   if not ready:
    if capture.poll() is not None:break
    continue
   chunk=os.read(capture.stdout.fileno(),262144)
   if not chunk:break
   buffer.extend(chunk)
   if not header and len(buffer)>=8:
    if bytes(buffer[:8])!=MAGIC:raise ValueError('invalid recorder header')
    compressor.stdin.write(MAGIC);del buffer[:8];header=True
   while header and len(buffer)>=4:
    n=struct.unpack('<I',buffer[:4])[0]
    if not 0<n<=MAX_FRAME:raise ValueError('invalid binary frame')
    if len(buffer)<4+n:break
    compressor.stdin.write(buffer[:4+n]);row=decode(bytes(buffer[4:4+n]));del buffer[:4+n];kind=row.get('kind','unknown');counts[kind]+=1;last[kind]=row.get('recv_ns',time.time_ns())
    if row.get('symbol'):symbols[row['symbol']]+=1
    recovery.state.observe(row)
  if stop_requested and capture.poll()is None:capture.terminate()
  if buffer and not stop_requested:raise ValueError('truncated recorder tail')
  if capture.wait(timeout=10)!=0 and not stop_requested:raise RuntimeError('recorder exited with error')
 except Exception as exc:error=str(exc)
 finally:
  recovery.close()
  if recovery.state.ready:recovery.state.invalidate('capture_stopped'if stop_requested else'capture_finished')
  for name,p in children:
   if name!='compressor' and p.poll() is None:p.terminate()
  if compressor:
   compressor.stdin.close()
   try:compressor.wait(timeout=20)
   except subprocess.TimeoutExpired:compressor.kill();compressor.wait()
  for name,p in children:
   if p.poll() is None:
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:p.kill();p.wait()
  save(True)
  for f in handles:f.close()
 if error:raise RuntimeError(error)
if __name__=='__main__':main()
