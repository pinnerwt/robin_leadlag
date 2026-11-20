"""Bounded startup storage discovery by local execution, pinned to code anchor."""
import json,re
from pathlib import Path
from bootstrap_state import Bootstrap
from probe_delegated_kind8 import run
PATH=Path('reports/amm/variant-code-checkpoint.json')
def main():
 seed=json.loads(PATH.read_text());seed['trace_execution']=True
 prior=json.loads(Path('reports/amm/variant-external-prefix.json').read_text());tx=prior['tx'];caller=tx['from'].lower()
 seed['accounts'][caller]=dict(code='0x',balance='0x0',nonce='0x0',storage={})
 b=Bootstrap('https://rpc-robinhood.blockmachine.io');reads=[];stages=[];block=seed['anchor']['number']
 for _ in range(20):
  r=run(seed,tx);stages.append(r);error=r.get('error') or ''
  missing=re.search(r'unknown slot (0x[0-9a-fA-F]{40}) (0x[0-9a-fA-F]+)',error)
  if missing:
   address,slot=missing[1].lower(),missing[2];value=b.rpc('eth_getStorageAt',[address,slot,block]);seed['accounts'][address]['storage'][slot]=value;reads.append(dict(address=address,slot=slot,value=value));continue
  break
 verified=b.rpc('eth_getBlockByNumber',[block,False])['hash']==seed['anchor']['hash']
 Path('reports/amm/variant-external-storage-prefix.json').write_text(json.dumps(dict(seed=seed,tx=tx,stages=stages,result=r,reads=reads,anchor_verified=verified,synthetic_accounts=[caller],caveat='New checkpoint local prefix, not original transaction replay. Caller metadata synthetic. External calls remain intercepted.'),indent=2)+'\n')
 print(json.dumps(dict(reads=len(reads),verified=verified,error=r.get('error'),calls=r['calls'],output=r.get('output'))))
if __name__=='__main__':main()
