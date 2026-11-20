"""Bootstrap-only dependency closure using PRE-anchor push samples and pinned reads.
This tool is never imported by replay/capture. Unknown future state fails closed.
"""
import argparse,json,re,subprocess
from collections import defaultdict
from pathlib import Path
from bootstrap_state import Bootstrap,word
from bootstrap_batch import merge

p=argparse.ArgumentParser(description=__doc__);p.add_argument('checkpoint',type=Path);p.add_argument('transactions',type=Path)
p.add_argument('--rpc',default='https://rpc-robinhood.blockmachine.io');a=p.parse_args()
seed=json.loads(a.checkpoint.read_text());anchor=seed['anchor'];b=Bootstrap(a.rpc)
# Only transactions available before the initial checkpoint. No held-out future calls.
cut=int(anchor['timestamp'],16)
oracles={'0xe844701934d9c6085b292e428f41b911cc0b3872','0x30a88bf894d1b806125a23ebf23d715496fd7102'}
calls=[json.loads(l) for l in a.transactions.read_text().splitlines()]
calls=[c for c in calls if c['to'].lower() in oracles and cut-1800<=c['timestamp']<cut]
if not calls:raise ValueError('no pre-anchor update samples')
calls.extend(dict(to=pool['pool'],data='0xec069057',tx=pool['pool']) for pool in seed['pools'])
a.checkpoint.with_suffix('.before-hydration.json').write_text(json.dumps(seed,separators=(',',':')))
for iteration in range(16):
 proc=subprocess.run(['target/release/examples/check_calls',str(a.checkpoint)],input=''.join(json.dumps(c)+'\n' for c in calls),text=True,capture_output=True,check=True)
 missing=defaultdict(set);accounts=set();errors=[]
 for line in proc.stdout.splitlines():
  r=json.loads(line);error=r.get('error','')
  if m:=re.search(r'unknown slot (0x[0-9a-fA-F]{40}) (0x[0-9a-fA-F]+)',error):missing[m[1].lower()].add(m[2])
  elif m:=re.search(r'unknown account (0x[0-9a-fA-F]{40})',error):accounts.add(m[1].lower())
  elif error:errors.append(error)
 print('round',iteration,'missing_accounts',len(accounts),'missing_slots',sum(map(len,missing.values())),'other_errors',len(errors),flush=True)
 if not accounts and not missing:
  seed['hydration']=dict(rounds=iteration,sampled_calls=len(calls),rpc_calls=b.calls,unknown_errors=errors,pre_anchor_only=True)
  break
 for address in sorted(accounts|missing.keys()):
  keys=sorted(missing[address])
  try:
   proof=b.rpc('eth_getProof',[address,keys,anchor['number']])
   account=dict(balance=proof['balance'],nonce=int(proof['nonce'],16),storage={'0x'+word(int(r['key'],16)).hex():'0x'+word(int(r['value'],16)).hex() for r in proof['storageProof']})
  except RuntimeError as error:
   if 'historical state' not in str(error):raise
   account=dict(storage={'0x'+word(int(key,16)).hex():b.rpc('eth_getStorageAt',[address,key,anchor['number']]) for key in keys})
   if address in accounts:
    account.update(balance=b.rpc('eth_getBalance',[address,anchor['number']]),nonce=int(b.rpc('eth_getTransactionCount',[address,anchor['number']]),16))
  if address in accounts:account['code']=b.rpc('eth_getCode',[address,anchor['number']])
  merge(seed,{address:account})
 a.checkpoint.write_text(json.dumps(seed,separators=(',',':')))
else:raise ValueError('dependency closure did not converge')
verified=b.rpc('eth_getBlockByNumber',[anchor['number'],False])
if verified['hash']!=anchor['hash']:raise ValueError('anchor reorg')
seed['anchor_verified']=True;a.checkpoint.write_text(json.dumps(seed,separators=(',',':')))
print('hydrated',seed['hydration'],flush=True)
