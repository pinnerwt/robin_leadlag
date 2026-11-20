import json,pathlib,subprocess,shutil,datetime,math
C=pathlib.Path('captures/ohio-latest-20261119T2103Z');R=pathlib.Path('reports/ohio-latest-20261119T2103Z');b=json.load(open(C/'bounds.json'));old=pathlib.Path('reports/ohio-iex-first-20261119');origin=json.load(open(old/'window.json'))['origin_ns'];cutoff=origin+b['recovery']['intervals'][0]['end_mono_ns']-1_000_000_000
w=dict(origin_ns=origin,start_ns=1795098600000000000,end_ns=cutoff,split_ns=json.load(open(old/'window.json'))['end_ns'],download_cutoff_ns=b['cutoff_ns'],exclusion='Stop 1 second before first reported head discontinuity; no usable later checkpoint')
(R/'window.json').write_text(json.dumps(w,indent=2));print('window',datetime.datetime.fromtimestamp(cutoff/1e9,datetime.timezone.utc),flush=True)
for label in ['chain','iex']:
 source=C/(label+'-prefix.bin.zst');assert source.stat().st_size==b['files'][label]['bytes']
 with open(C/(label+'.bin.zst'),'wb')as output,open(R/(label+'-trim.json'),'wb')as log:
  dec=subprocess.Popen(['zstd','-q','-dc',str(source)],stdout=subprocess.PIPE,stderr=subprocess.PIPE);trim=subprocess.Popen(['target/release/examples/research_tape_window','recv_ns','1',str(cutoff)],stdin=dec.stdout,stdout=subprocess.PIPE,stderr=log);dec.stdout.close();enc=subprocess.Popen(['zstd','-q','-T1','-c'],stdin=trim.stdout,stdout=output);trim.stdout.close();assert enc.wait()==0;assert trim.wait()==0;error=dec.stderr.read().decode();status=dec.wait();assert status==0 or 'premature' in error.lower()or'unexpected end'in error.lower(),error
 print('trimmed',label,flush=True)
shutil.copy(old/'checkpoint.json',R/'checkpoint.json');subprocess.run(['python3','scripts/prepare_metric_pool_seeds.py','--capture',str(R),'--output',str(R)],check=True)
for m in json.load(open(R/'manifest.json')):
 p=pathlib.Path(m['seed']);s=json.load(open(p));prev=json.load(open(old/(m['symbol']+'-seed.json')))['pools'][0]
 if 'aux_feed_id'in prev:s['pools'][0]['aux_feed_id']=prev['aux_feed_id'];p.write_text(json.dumps(s))
dec=subprocess.Popen(['zstd','-q','-dc',str(C/'chain.bin.zst')],stdout=subprocess.PIPE);subprocess.run(['target/release/examples/prepare_recovery_causal',str(R)],stdin=dec.stdout,check=True);dec.stdout.close();assert dec.wait()==0
import sys
sys.path.insert(0,'scripts')
from iex_pool_hy import load_iex
from tape import records
series,bbos,quality=load_iex(records([C/'iex.bin.zst']));(R/'iex-quality.json').write_text(json.dumps(quality,indent=2))
for ticker,rows in bbos.items():
 rows=[dict(r,mono_ns=r['recv_ns']-origin) for r in rows if w['start_ns']<=r['recv_ns']<=cutoff]
 rows += [dict(recv_ns=t,mono_ns=t-origin,invalid=True) for t,b,a in series[ticker] if not math.isfinite(b) and w['start_ns']<=t<=cutoff]
 rows.sort(key=lambda r:r['recv_ns'])
 (R/(ticker+'-iex-bbo.jsonl')).write_text(''.join(json.dumps(r)+'\n'for r in rows))
print('prepared',flush=True)
