"""Finite wait/export/pull/verify/analyze job for this requested half-hour window."""
import datetime,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.chdir(root)
start_ns=int(datetime.datetime(2026,11,19,3,33,1,tzinfo=datetime.timezone.utc).timestamp())*10**9
end_ns=int(datetime.datetime(2026,11,19,4,3,1,tzinfo=datetime.timezone.utc).timestamp())*10**9
name='ohio-halfhour-20261119T040301Z';remote='exports/'+name;local=Path('captures')/name;analysis=Path('reports')/name
state=Path('reports/ohio-halfhour-job.json')
def save(phase,**kw):
 state.write_text(json.dumps(dict(phase=phase,updated_ns=time.time_ns(),start_ns=start_ns,end_ns=end_ns,**kw),indent=2)+'\n');print(phase,flush=True)
def run(args,**kw):subprocess.run(args,check=True,**kw)
save('waiting_for_half_hour')
while time.time_ns()<end_ns:
 time.sleep(min(30,(end_ns-time.time_ns())/1e9))
try:
 save('exporting_complete_records')
 run(['ssh','robin','cd /home/ubuntu/robin_leadlag && nice -n 15 python3 scripts/export_ohio_research.py '+remote+' --cutoff-ns '+str(end_ns)])
 save('downloading')
 run(['scp','-r','robin:/home/ubuntu/robin_leadlag/'+remote,str(local)])
 save('verifying_checksums')
 manifest=json.load(open(local/'manifest.json'))
 for filename,expected in manifest['files'].items():
  p=local/filename;h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
  assert p.stat().st_size==expected['size'] and h.hexdigest()==expected['sha256'],filename
 analysis.mkdir(parents=True,exist_ok=True);oracle=analysis/'oracle';oracle.mkdir(exist_ok=True)
 shutil.copyfile('reports/metric-20261117-source-hy/manifest.json',oracle/'manifest.json')
 save('extracting_oracle_source')
 dec=subprocess.Popen(['zstd','-q','-dc',str(local/'robinhood.bin.zst')],stdout=subprocess.PIPE)
 try:run(['target/release/examples/source_hy_extract',str(oracle),'--wall-clock'],stdin=dec.stdout)
 finally:dec.stdout.close()
 assert dec.wait()==0,'decompression failed'
 save('calculating_hy')
 paths=[str(p) for p in sorted(local.glob('ohio-equity-*.bin.zst'))]
 run(['/home/pgi/mid_freq/.venv/bin/python','scripts/ohio_spot_hy.py',*paths,'--start-ns',str(start_ns),'--end-ns',str(end_ns),'--oracle-directory',str(oracle),'--output',str(analysis)])
 save('complete',analysis=str(analysis),download=str(local),checksum_verified=True)
except Exception as exc:
 save('failed',error=str(exc));raise
