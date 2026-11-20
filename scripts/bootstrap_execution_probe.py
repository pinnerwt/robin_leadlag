"""Initialization-only full-call dependency probe at ONE fixed block.
Not historical replay: old calldata is probed against the explicitly selected
snapshot. Does not establish complete future-state coverage. Never run on hot path.
"""
import argparse,json,time
from pathlib import Path
from bootstrap_state import Bootstrap
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rpc',default='https://rpc-robinhood.blockmachine.io');p.add_argument('--block',default='latest');p.add_argument('--corpus',default='reports/amm/packed-router-corpus.jsonl');p.add_argument('--output',default='captures/full-execution-probe.json');p.add_argument('--limit',type=int,default=3);a=p.parse_args()
b=Bootstrap(a.rpc);head=b.rpc('eth_getBlockByNumber',[a.block,False]);seed=dict(anchor=head,accounts={},probes=[],rpc_phase='initialization_only',historical_replay=False,complete=False,created_ns=time.time_ns());seen=set()
for line in open(a.corpus):
 row=json.loads(line);tx=row.get('tx',row);key=(tx['to'].lower(),tx['data'][:10])
 if key in seen:continue
 seen.add(key)
 call={k:tx[k] for k in ('from','to','data','value')};call['gas']='0x1c9c380'
 try:
  accounts=b.rpc('debug_traceCall',[call,head['number'],{'tracer':'prestateTracer'}])
  if not isinstance(accounts,dict) or any(not k.startswith('0x') for k in accounts):raise ValueError('unexpected prestate result')
  for address,account in accounts.items():
   address=address.lower();dst=seed['accounts'].setdefault(address,{})
   for key,value in account.items():
    if key=='storage':
     target=dst.setdefault('storage',{})
     for slot,v in value.items():
      if slot in target and target[slot]!=v:raise ValueError('inconsistent pinned storage')
      target[slot]=v
    else:
     if key in dst and dst[key]!=value:raise ValueError('inconsistent pinned account')
     dst[key]=value
  seed['probes'].append(dict(tx=tx,accounts=len(accounts),status='dependencies_at_anchor_not_original_execution'))
 except Exception as e:seed['probes'].append(dict(tx=tx,error=str(e)))
 Path(a.output).write_text(json.dumps(seed,indent=2)+'\n')
 print(json.dumps({k:v for k,v in seed['probes'][-1].items() if k!='tx'}),flush=True)
 if len(seed['probes'])>=a.limit:break
seed['rpc_calls']=b.calls;Path(a.output).write_text(json.dumps(seed,indent=2)+'\n')
