"""Setup-only strict dependency closure for local router prefix execution.
Uses calldata and fixed-block code/storage, never swap logs to derive arguments.
"""
import json,re,subprocess,sys,time
from pathlib import Path
from collections import defaultdict
from bootstrap_state import Bootstrap
b=Bootstrap('https://rpc-robinhood.blockmachine.io');existing=Path('captures/router-prefix-checkpoint.json');saved=json.loads(existing.read_text()) if '--resume' in sys.argv and existing.exists() else None;head=saved['anchor'] if saved else b.rpc('eth_getBlockByNumber',['latest',False]);block=head['number']
codes=json.load(open('reports/amm/router-code.json'))['code'];txs=[]
for line in open('reports/amm/packed-router-corpus.jsonl'):
 r=json.loads(line);txs.append(r['tx'])
# Chronological suffix reserved for independent decoding validation.
train=txs[:len(txs)*3//5];Path('/tmp/router-prefix-train.jsonl').write_text(''.join(json.dumps(t)+'\n' for t in train))
seed={'anchor':head,'accounts':{},'getters':{},'rpc_phase':'bootstrap_only','training_transactions':len(train),'created_ns':time.time_ns()}
for a in ([] if saved else codes):
 code=b.rpc('eth_getCode',[a,block]);assert code==codes[a],'router code changed; re-audit required'
 proof=b.rpc('eth_getProof',[a,[],block]);seed['accounts'][a]={'code':code,'balance':proof['balance'],'nonce':int(proof['nonce'],16),'storage':{}}
if saved:seed=saved
p=Path('captures/router-prefix-checkpoint.json')
for iteration in range(20):
 p.write_text(json.dumps(seed,indent=2)+'\n')
 with open('/tmp/router-prefix-train.jsonl') as f:
  proc=subprocess.run(['target/release/examples/router_prefix',str(p)],stdin=f,text=True,capture_output=True,check=True)
 missing=defaultdict(set);accounts=set();other=[];calls=0
 for l in proc.stdout.splitlines():
  r=json.loads(l);calls+=bool(r['calls']);error=r.get('error')
  if error:
   m=re.search(r'unknown slot (0x[0-9a-fA-F]+) (0x[0-9a-fA-F]+)',error)
   a=re.search(r'unknown account (0x[0-9a-fA-F]+)',error)
   if m:missing[m[1].lower()].add(m[2])
   elif a:accounts.add(a[1].lower())
   else:other.append(error)
 print('round',iteration,'calls',calls,'missing slots',sum(map(len,missing.values())),'accounts',len(accounts),'other',other[:2],flush=True)
 if not missing and not accounts:break
 for address in missing.keys()|accounts:
  slots=sorted(missing[address]);new=address not in seed['accounts']
  dst=seed['accounts'].setdefault(address,{'storage':{}})
  try:
   if seed.get('proof_unavailable'):raise RuntimeError('historical state proof unavailable')
   proof=b.rpc('eth_getProof',[address,slots,block]);dst.update(balance=proof['balance'],nonce=int(proof['nonce'],16))
   for slot in proof['storageProof']:dst['storage'][hex(int(slot['key'],16))]=slot['value']
  except RuntimeError as error:
   if not any(x in str(error) for x in ['historical state','missing trie node','maximum proof window']):raise
   seed['proof_unavailable']=True
   for slot in slots:dst['storage'][slot]=b.rpc('eth_getStorageAt',[address,slot,block])
   if new:dst.update(balance=b.rpc('eth_getBalance',[address,block]),nonce=int(b.rpc('eth_getTransactionCount',[address,block]),16))
  if new:dst['code']=b.rpc('eth_getCode',[address,block])
  p.write_text(json.dumps(seed,indent=2)+'\n')

else:raise RuntimeError('bootstrap dependency closure exceeded iteration limit')
seed['rpc_calls']=b.calls;seed['complete_prefix_dependencies']=not other;seed['completed_ns']=time.time_ns();p.write_text(json.dumps(seed,indent=2)+'\n')
print('complete',seed['complete_prefix_dependencies'],'rpc calls',b.calls,flush=True)
