"""Pinned fresh swap dependency discovery; intentionally unfunded, no tx sent."""
import argparse,json
from pathlib import Path
from bootstrap_state import Bootstrap,word,unpack
from bootstrap_index4_observations import POOL
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('observations');ap.add_argument('--rpc',default='https://rpc.mainnet.chain.robinhood.com');ap.add_argument('--output',required=True);a=ap.parse_args()
obs=json.load(open(a.observations));head=obs['anchor'];block=head['number'];b=Bootstrap(a.rpc,interval=.5)
if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=head['hash']:raise ValueError('anchor mismatch')
sqrt=unpack(obs['slot0'])[0];caller='0x1111111111111111111111111111111111111111'
# Small USDG-input swap, no callback funding. Capture actual economic reads up
# to settlement rejection; execution success must NOT be inferred from prestate.
data='0x128acb08'+b''.join(word(v) for v in [int(caller,16),0,16777216,sqrt*1001//1000,160,0]).hex()
call=dict(to=POOL,from_=caller,data=data,gas='0x1c9c380');call['from']=call.pop('from_')
accounts=b.rpc('debug_traceCall',[call,block,{'tracer':'prestateTracer'}])
if not isinstance(accounts,dict) or any(not k.startswith('0x') for k in accounts):raise ValueError('invalid prestate')
trace=b.rpc('debug_traceCall',[call,block,{'tracer':'callTracer'}])
if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=head['hash']:raise ValueError('anchor changed')
for address,account in obs['accounts'].items():
 target=accounts.setdefault(address,{}).setdefault('storage',{})
 existing={int(k,16):int(v,16) for k,v in target.items()}
 for key,value in account['storage'].items():
  if int(key,16) in existing and existing[int(key,16)]!=int(value,16):raise ValueError('inconsistent observation')
  target[hex(int(key,16))]=hex(int(value,16))
result=dict(anchor=head,parent_header=head,accounts=accounts,call=call,trace=trace,complete=False,execution_state_complete=False,historical_replay=False,rpc_phase='initialization_only',rpc_calls=b.calls)
Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(accounts=len(accounts),storage_slots=sum(len(x.get('storage',{})) for x in accounts.values()),error=trace.get('error'),output=trace.get('output'),rpc_calls=b.calls)))
