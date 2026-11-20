"""Refresh observed dependency keys at the quote checkpoint's single anchor.

Historical witnesses supply keys only, never values. This is initialization,
not a runtime missing-state resolver, and does not claim exhaustive coverage.
"""
import argparse,json,re,time,hashlib
from pathlib import Path
from bootstrap_state import Bootstrap
from bootstrap_accounts import read_accounts
from bootstrap_storage import read_slots
from bootstrap_proxies import hydrate_proxies
from bootstrap_router_mappings import add_mapping_keys

ADDRESS=re.compile(r'^0x[0-9a-fA-F]{40}$')

def inventory(value,keys):
 if isinstance(value,dict):
  for address,account in value.items():
   if ADDRESS.fullmatch(address) and isinstance(account,dict) and any(k in account for k in ('storage','code','nonce','balance')):
    keys.setdefault(address.lower(),set()).update(int(k,16) for k in account.get('storage',{}))
   inventory(account,keys)
 elif isinstance(value,list):
  for item in value:inventory(item,keys)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('checkpoint',type=Path);p.add_argument('--source',action='append',default=[])
 p.add_argument('--actors',type=Path);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--fixed-slot-prefix',type=int,default=0,help='Initialize slots [0,N) on observed code accounts; values are queried, never inferred')
 p.add_argument('--dependency-anchor',type=Path,help='Read only dependency keys from checkpoint; hydrate at this new header concurrently with a separate quote bootstrap')
 p.add_argument('--router-mappings',type=Path)
 p.add_argument('--rpc',default='https://rpc-robinhood.blockmachine.io');p.add_argument('--rpc-interval',type=float,default=.5)
 a=p.parse_args();seed=json.loads(a.checkpoint.read_text())
 if not seed.get('quote_state_complete'):raise ValueError('source quote checkpoint incomplete')
 keys={};inventory(seed,keys)
 # Precompiles can hold native balances too; never infer empty account state.
 for number in range(11):keys.setdefault('0x'+number.to_bytes(20,'big').hex(),set())
 keys.setdefault('0xa4b0500000000000000000000000000000000001',set())
 if a.dependency_anchor:
  head=json.loads(a.dependency_anchor.read_text())
  seed=dict(anchor=head,parent_header=head,accounts={},pools=[],quote_state_complete=False,complete=False,kind='dependency_checkpoint')
 if not 0<=a.fixed_slot_prefix<=256:raise ValueError('fixed-slot-prefix must be between 0 and 256')
 for path in a.source:
  source=json.loads(Path(path).read_text())
  if isinstance(source,dict) and source.get('kind')=='dependency_keys_only':
   if not source.get('complete'):raise ValueError('dependency training incomplete')
   if int(source['training_tip']['number'],16)>=int(seed['anchor']['number'],16):raise ValueError('training must precede quote anchor')
  inventory(source,keys)
 if a.actors:
  with a.actors.open() as f:
   for line in f:
    tx=json.loads(line)
    if 'sequence' in tx and tx['sequence']>=int(seed['anchor']['number'],16):raise ValueError('actor discovery must precede initialization anchor')
    for field in ('from','to'):
     address=tx.get(field)
     if isinstance(address,str) and ADDRESS.fullmatch(address):keys.setdefault(address.lower(),set())
 block=seed['anchor']['number'];b=Bootstrap(a.rpc,interval=a.rpc_interval)
 # All hydration calls are pinned to this anchor. Cache successful responses
 # so a diagnostic retry need not repeat thousands of already verified reads.
 cache=a.output.with_suffix('.rpc-cache');cache.mkdir(exist_ok=True)
 original_rpc=b.rpc
 def cached_rpc(method,params):
  key=hashlib.sha256(json.dumps([seed['anchor']['hash'],method,params],sort_keys=True).encode()).hexdigest();path=cache/(key+'.json')
  if path.exists():return json.loads(path.read_text())
  result=original_rpc(method,params);path.write_text(json.dumps(result));return result
 b.rpc=cached_rpc
 print('hydrate',block,'accounts',len(keys),'slots',sum(map(len,keys.values())),flush=True)
 # Retain no historical values and no simulated getter side effects.
 accounts=read_accounts(b,block,keys)
 accounts={address:{k:v for k,v in account.items() if k!='storage'} for address,account in accounts.items()}
 print('metadata complete',len(accounts),'calls',b.calls,flush=True)
 mapping_evidence=add_mapping_keys(b,block,accounts,keys,a.router_mappings) if a.router_mappings else []
 if a.fixed_slot_prefix:
  for address,account in accounts.items():
   if account.get('code','0x')!='0x' and int(address,16)>0xffff and address!='0xa4b05fffffffffffffffffffffffffffffffffff':
    keys.setdefault(address,set()).update(range(a.fixed_slot_prefix))
  print('expanded explicit slots',sum(map(len,keys.values())),flush=True)
 slots=read_slots(b.rpc,block,{address:sorted(values) for address,values in keys.items() if values})
 for address,values in slots.items():accounts[address]['storage']=values
 references=hydrate_proxies(b,block,accounts)
 # Quote snapshot must agree with independently refreshed execution storage.
 for address,account in seed['accounts'].items():
  for key,value in account.get('storage',{}).items():
   if int(accounts[address.lower()]['storage'][hex(int(key,16))],16)!=int(value,16):
    raise ValueError(f'checkpoint storage disagreement {address} {key}')
 head=b.rpc('eth_getBlockByNumber',[block,False])
 if head['hash']!=seed['anchor']['hash']:raise ValueError('anchor changed')
 seed.update(accounts=accounts,parent_header=head,execution_state_complete=False,
  evm_dependency_coverage='historically_observed_keys_refreshed_at_single_anchor',
  hydration={'sources':a.source,'actors':str(a.actors),'fixed_slot_prefix':a.fixed_slot_prefix,'router_mapping_queries':mapping_evidence,'proxy_references':references,'rpc_calls':b.calls,'completed_ns':time.time_ns()})
 a.output.write_text(json.dumps(seed,separators=(',',':'))+'\n')
 print('saved',a.output,'calls',b.calls,flush=True)

if __name__=='__main__':main()
