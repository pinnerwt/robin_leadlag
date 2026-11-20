"""Initialization/research only: recent boundary witnesses for StartBlock audit."""
import json,subprocess
from pathlib import Path
from bootstrap_state import Bootstrap
b=Bootstrap('https://rpc-robinhood.blockmachine.io');tip=b.rpc('eth_getBlockByNumber',['latest',False]);n=int(tip['number'],16);cache={n:tip};reports=[]
def head(number):
 if number not in cache:cache[number]=b.rpc('eth_getBlockByNumber',[hex(number),False])
 return cache[number]
for name,key in [('second','timestamp'),('l1','l1BlockNumber')]:
 target=int(tip[key],16);lo=n-2048;hi=n
 if int(head(lo)[key],16)>=target:raise ValueError('boundary outside recent search window')
 while hi-lo>1:
  mid=(hi+lo)//2
  if int(head(mid)[key],16)<target:lo=mid
  else:hi=mid
 h=head(hi);parent=head(hi-1)
 pre=b.rpc('debug_traceBlockByHash',[h['hash'],{'tracer':'prestateTracer'}]);diff=b.rpc('debug_traceBlockByHash',[h['hash'],{'tracer':'prestateTracer','tracerConfig':{'diffMode':True}}]);assert pre[0]['txHash']==h['transactions'][0]==diff[0]['txHash']
 f=dict(header=h,parent=parent,system_accounts=pre[0]['result'],system_diff=diff[0]['result'],system_tx=pre[0]['txHash']);path=Path('captures/system-start-'+name+'.json');path.write_text(json.dumps(f,indent=2)+'\n')
 p=subprocess.run(['target/release/examples/arbos_start',str(path)],text=True,capture_output=True);r=json.loads(p.stdout) if p.returncode==0 else {}
 expected={a:{hex(int(k,16)):hex(int(v,16)) for k,v in x.get('storage',{}).items()} for a,x in f['system_diff']['post'].items() if x.get('storage')}
 for a,x in f['system_diff']['pre'].items():
  for k in x.get('storage',{}):
   if k not in f['system_diff']['post'].get(a,{}).get('storage',{}):expected.setdefault(a,{})[hex(int(k,16))]='0x0'
 row=dict(case=name,block=h['number'],elapsed=int(h['timestamp'],16)-int(parent['timestamp'],16),l1_delta=int(h['l1BlockNumber'],16)-int(parent['l1BlockNumber'],16),matched=p.returncode==0 and r['writes']==expected and int(r['current_base_fee'],16)==int(h['baseFeePerGas'],16),local=r,expected=expected,error=p.stderr)
 reports.append(row);Path('reports/amm/start-block-boundary-parity.json').write_text(json.dumps(reports,indent=2)+'\n');print({k:v for k,v in row.items() if k not in ('local','expected')},flush=True)
if not all(r['matched'] for r in reports):raise SystemExit('StartBlock mismatch')
