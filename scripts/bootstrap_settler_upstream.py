"""Bounded new-anchor initialization for missing first upstream V4 pool.
Separate artifact only; never merge new state into archived replay checkpoint.
"""
import json
from pathlib import Path
from bootstrap_state import Bootstrap,mapping,hashhex,word
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'
def main():
 plan=json.loads(Path('reports/amm/delegated-batch-route-plans.json').read_text())['transactions'][0]['plan']['v4'];hook=plan['hook']
 poolid=int(hashhex(b''.join(word(x) for x in [int(plan['currency0'],16),int(plan['currency1'],16),plan['fee'],plan['spacing'],int(hook,16)])),16)
 base=int(mapping(poolid,6),16);config=int(mapping(poolid,10),16)
 b=Bootstrap('https://rpc-robinhood.blockmachine.io');reads=[];accounts={};anchor=None;error=None;verified=False
 def storage(address,slot):
  if b.calls>=55:raise ValueError('initialization request bound reached')
  key=hex(slot);existing=accounts[address]['storage']
  if key in existing:return int(existing[key],16)
  value=b.rpc('eth_getStorageAt',[address,key,anchor['number']]);existing[key]=value;reads.append(dict(address=address,slot=key,value=value));return int(value,16)
 try:
  anchor=b.rpc('eth_getBlockByNumber',['latest',False]);old=json.loads(Path('captures/startup-v9-dependencies.json').read_text());code_matches={}
  for address in (MANAGER,hook):
   code=b.rpc('eth_getCode',[address,anchor['number']]);balance=b.rpc('eth_getBalance',[address,anchor['number']]);nonce=b.rpc('eth_getTransactionCount',[address,anchor['number']])
   accounts[address]=dict(code=code,balance=balance,nonce=nonce,storage={});code_matches[address]=code.lower()==old['accounts'][address]['code'].lower()
  for i in range(4):storage(MANAGER,base+i)
  for i in range(5):storage(hook,config+i)
  for slot in (12,13):storage(hook,int(mapping(0,int(mapping(poolid,slot),16)),16))
  slot0=int(accounts[MANAGER]['storage'][hex(base)],16);tick=(slot0>>160)&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
  center=(tick//plan['spacing'])>>8;initialized=[]
  for index in range(center-1,center+2):
   bitmap=storage(MANAGER,int(mapping(index,base+5),16))
   for bit in range(256):
    if bitmap&(1<<bit):initialized.append((index*256+bit)*plan['spacing'])
  for tick in initialized:storage(MANAGER,int(mapping(tick,base+4),16))
  verified=b.rpc('eth_getBlockByNumber',[anchor['number'],False])['hash']==anchor['hash']
 except Exception as exc:error=str(exc);print(error,flush=True)
 report=dict(seed=dict(anchor=anchor,accounts=accounts),poolid=hex(poolid),plan=plan,reads=reads,code_matches=locals().get('code_matches',{}),anchor_verified=verified,error=error,rpc_calls=b.calls,
  caveat='New initialization anchor, separate from archived corpus. Bounded bitmap window; missing slots remain unknown. No historical parity, complete execution state or production activation claim.')
 Path('reports/amm/settler-upstream-new-checkpoint.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(anchor=anchor and anchor['number'],reads=len(reads),calls=b.calls,verified=verified,error=error)),flush=True)
if __name__=='__main__':main()
