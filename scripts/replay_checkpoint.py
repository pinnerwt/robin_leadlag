"""Offline held-out replay runner. No network imports or missing-state recovery."""
import argparse,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('checkpoint',type=Path);p.add_argument('decoded',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
seed=json.loads(a.checkpoint.read_text());anchor=int(seed['anchor']['number'],16);first=None
output=a.output.with_suffix('.jsonl');errors=a.output.with_suffix('.stderr');start=time.monotonic_ns()
with output.open('w') as out,errors.open('w') as err:
 proc=subprocess.Popen(['target/release/examples/router_execute',str(a.checkpoint),'--commit','--units-mode=signed','--block-mode','--require-filter-state'],stdin=subprocess.PIPE,stdout=out,stderr=err,text=True)
 try:
  with a.decoded.open() as source:
   for line in source:
    row=json.loads(line)
    if row.get('kind') not in ('feed_block','feed_tx','feed_system_tx') or row['sequence']<=anchor:continue
    if first is None:first=row['sequence']
    proc.stdin.write(line)
 except BrokenPipeError:pass
 finally:
  try:proc.stdin.close()
  except BrokenPipeError:pass
  status=proc.wait()
counts={'blocks_started':0,'committed_transactions':0,'committed_system_transactions':0,'pool_writing_transactions':0};last=None;failure=None;pools={x['pool'].lower() for x in seed['pools']}
with output.open() as source:
 for line in source:
  r=json.loads(line);last=r.get('sequence',last)
  if r.get('kind')=='block_state':counts['blocks_started']+=1
  elif r.get('committed'):
   counts['committed_system_transactions' if r.get('kind')=='system_state' else 'committed_transactions']+=1
   if pools.intersection(r.get('changed_storage',{})):counts['pool_writing_transactions']+=1
  if r.get('error'):failure={'sequence':r.get('sequence'),'tx':r.get('tx'),'error':r['error']}
report=dict(checkpoint=str(a.checkpoint),anchor=anchor,anchor_hash=seed['anchor']['hash'],first_sequence=first,last_sequence=last,
 counts=counts,engine_exit=status,first_failure=failure,stderr=errors.read_text(),elapsed_ns=time.monotonic_ns()-start,
 runtime_rpc_calls=0,input_consumed_without_execution_error=status==0,chain_state_parity_verified=False,
 production_ready=False,accounts=len(seed['accounts']),slots=sum(len(x.get('storage',{})) for x in seed['accounts'].values()))
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if status:raise SystemExit(status)
