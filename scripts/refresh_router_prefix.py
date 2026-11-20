"""Initialization-only refresh, reusing discovered dependency KEYS, not old values."""
import json,re,subprocess,time
from pathlib import Path
from collections import defaultdict
from bootstrap_state import Bootstrap
p=Path('captures/router-prefix-checkpoint.json');old=json.loads(p.read_text());keys=defaultdict(set)
for a,v in old['accounts'].items():keys[a].update(v['storage'])
with open('/tmp/router-prefix-train.jsonl') as f:r=subprocess.run(['target/release/examples/router_prefix',str(p)],stdin=f,text=True,capture_output=True,check=True)
for l in r.stdout.splitlines():
 e=json.loads(l).get('error') or ''
 if m:=re.search(r'unknown slot (0x[0-9a-fA-F]+) (0x[0-9a-fA-F]+)',e):keys[m[1].lower()].add(m[2])
 elif m:=re.search(r'unknown account (0x[0-9a-fA-F]+)',e):keys[m[1].lower()]
b=Bootstrap('https://rpc-robinhood.blockmachine.io');head=b.rpc('eth_getBlockByNumber',['latest',False]);block=head['number'];seed=dict(anchor=head,accounts={},getters={},rpc_phase='bootstrap_only',created_ns=time.time_ns(),training_transactions=old['training_transactions'])
p.with_suffix('.previous.json').write_text(json.dumps(old))
for a,slots in sorted(keys.items(),key=lambda x:-len(x[1])):
 try:
  proof=b.rpc('eth_getProof',[a,sorted(slots),block]);account=dict(balance=proof['balance'],nonce=int(proof['nonce'],16),storage={hex(int(v['key'],16)):v['value'] for v in proof['storageProof']})
 except RuntimeError as e:
  if not any(s in str(e) for s in ('historical state','trie node','proof window')):raise
  account=dict(balance=b.rpc('eth_getBalance',[a,block]),nonce=int(b.rpc('eth_getTransactionCount',[a,block]),16),storage={k:b.rpc('eth_getStorageAt',[a,k,block]) for k in slots})
 account['code']=b.rpc('eth_getCode',[a,block]);seed['accounts'][a]=account
 p.write_text(json.dumps(seed,indent=2)+'\n');print('refreshed',a,'slots',len(slots),flush=True)
print('refresh done',len(keys),'slots',sum(map(len,keys.values())),flush=True)
