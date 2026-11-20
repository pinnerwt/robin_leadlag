"""Initialization-only fixed-block validation of full local execution probes."""
import json
from pathlib import Path
from collections import Counter
from bootstrap_state import Bootstrap
seed=json.load(open('captures/full-execution-probe.json'));local={r['tx']:r for r in map(json.loads,open('reports/amm/full-execution-probes.jsonl'))};b=Bootstrap('https://rpc-robinhood.blockmachine.io');out=[]
def logs(frame):
 if frame.get('error'):return []
 return frame.get('logs',[])+[l for c in frame.get('calls',[]) for l in logs(c)]
def bag(items):return Counter((x['address'].lower(),tuple(t.lower() for t in x['topics']),x['data'].lower()) for x in items)
for r in seed['probes']:
 tx=r['tx'];call={k:tx[k] for k in ('from','to','data','value')};call['gas']='0x1c9c380'
 trace=b.rpc('debug_traceCall',[call,seed['anchor']['number'],{'tracer':'callTracer','tracerConfig':{'withLog':True}}]);got=local[tx['tx']]
 diff=b.rpc('debug_traceCall',[call,seed['anchor']['number'],{'tracer':'prestateTracer','tracerConfig':{'diffMode':True}}])
 expected_storage={}
 for address,account in diff.get('post',{}).items():
  if account.get('storage'):expected_storage[address.lower()]={hex(int(k,16)):hex(int(v,16)) for k,v in account['storage'].items()}
 # Slots cleared to zero may only appear in pre.
 for address,account in diff.get('pre',{}).items():
  for slot in account.get('storage',{}):
   if slot not in diff.get('post',{}).get(address,{}).get('storage',{}):expected_storage.setdefault(address.lower(),{})[hex(int(slot,16))]='0x0'
 expected=logs(trace);checks=dict(success=got['success']==(not bool(trace.get('error'))),output=got['output']==trace.get('output','0x'),log_multiset=bag(got['logs'])==bag(expected),no_missing_state=got['error'] is None,changed_storage=got['changed_storage']==expected_storage)
 checks['non_arbos_changed_storage']={k:v for k,v in expected_storage.items() if k!='0xa4b05fffffffffffffffffffffffffffffffffff'}=={k:v for k,v in got['changed_storage'].items() if k!='0xa4b05fffffffffffffffffffffffffffffffffff'}
 out.append(dict(tx=tx['tx'],router=tx['to'],checks=checks,local_success=got['success'],logs=len(expected),trace=trace,state_diff=diff,expected_storage=expected_storage,local_storage=got['changed_storage']));print(tx['to'],checks,flush=True)
Path('reports/amm/full-execution-parity.json').write_text(json.dumps(dict(anchor=seed['anchor']['number'],historical_replay=False,continuous_state=False,probes=out),indent=2)+'\n')
if not all(all(r['checks'].values()) for r in out):raise SystemExit('probe mismatch')
