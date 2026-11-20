"""Initialization training only: collect keys from executed PRE-anchor blocks.
No witnessed values are retained. A later checkpoint must refresh every value.
"""
import argparse,json,time,subprocess
from pathlib import Path
from bootstrap_state import Bootstrap
from dependency_coverage import select_blocks
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--blocks',type=int,default=64);p.add_argument('--output',type=Path,required=True);p.add_argument('--discover-caller-maps',type=Path)
p.add_argument('--decoded',type=Path,action='append',help='Select representative router/caller/selector routes from pre-anchor feed instead of consecutive blocks')
p.add_argument('--window',type=int,default=1500);a=p.parse_args()
b=Bootstrap('https://rpc-robinhood.blockmachine.io',interval=.5);head=b.rpc('eth_getBlockByNumber',['latest',False]);tip=int(head['number'],16);accounts={};traces=0
result=dict(kind='dependency_keys_only',training_tip=head,accounts=accounts,blocks=[],complete=False);contexts=[]
numbers=list(range(tip-a.blocks+1,tip+1))
if a.decoded:
 def lines():
  for path in a.decoded:
   with path.open() as source:yield from source
 coverage=select_blocks(lines(),tip,a.blocks,a.window);result['coverage']=coverage;numbers=sorted(coverage['selected_blocks'])
 if not numbers:raise ValueError('no eligible pre-anchor blocks in supplied feed')
 a.output.write_text(json.dumps(result))
 print('selected blocks',len(numbers),'covered routes',coverage['covered_routes'],'of',coverage['eligible_routes'],flush=True)
for number in numbers:
 rows=b.rpc('debug_traceBlockByNumber',[hex(number),{'tracer':'prestateTracer'}])
 if a.discover_caller_maps:
  header=b.rpc('eth_getBlockByNumber',[hex(number),True]);transactions={t['hash']:t for t in header['transactions']}
 for row in rows:
  if row.get('error'):raise ValueError(row['error'])
  if a.discover_caller_maps:
   tx=transactions.get(row['txHash']);target=(tx.get('to') or '').lower() if tx else ''
   account=row['result'].get(target,{})
   if account.get('storage') and account.get('code'):
    contexts.append(dict(router=target,caller=tx['from'].lower(),code=account['code'],keys=list(account['storage'])))
  for address,account in row['result'].items():
   dst=accounts.setdefault(address.lower(),{'storage':{}})
   dst['storage'].update({k:None for k in account.get('storage',{})})
  traces+=1
 result['blocks'].append(number);result['transactions']=traces;result['rpc_calls']=b.calls;a.output.write_text(json.dumps(result))
 if len(result['blocks'])%8==0:print('training blocks',len(result['blocks']),'accounts',len(accounts),'slots',sum(len(v['storage']) for v in accounts.values()),flush=True)
result.update(complete=True,completed_ns=time.time_ns());a.output.write_text(json.dumps(result));print('training complete',traces,'transactions',flush=True)
if a.discover_caller_maps:
 proc=subprocess.run(['target/release/examples/discover_caller_maps'],input=json.dumps(contexts),text=True,capture_output=True,check=True)
 a.discover_caller_maps.write_text(proc.stdout);print('caller mapping candidates',len(json.loads(proc.stdout)),flush=True)
