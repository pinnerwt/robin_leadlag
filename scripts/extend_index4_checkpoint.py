"""Explicit initialization-only account/slot extension at an existing anchor."""
import argparse,json
from pathlib import Path
from bootstrap_state import Bootstrap
from bootstrap_storage import read_slots
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('checkpoint');ap.add_argument('--address',action='append',default=[]);ap.add_argument('--slot',action='append',default=[]);a=ap.parse_args()
p=Path(a.checkpoint);s=json.loads(p.read_text());b=Bootstrap('https://rpc.mainnet.chain.robinhood.com',interval=.1);block=s['anchor']['number']
if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=s['anchor']['hash']:raise ValueError('anchor mismatch')
keys={}
for address in a.address:
 address=address.lower()
 if address in s['accounts']:raise ValueError('account already present: use --slot')
 account=dict(code=b.rpc('eth_getCode',[address,block]),balance=b.rpc('eth_getBalance',[address,block]),nonce=int(b.rpc('eth_getTransactionCount',[address,block]),16))
 s['accounts'][address]=account
 if account['code']!='0x':keys[address]=list(range(32))
for spec in a.slot:
 address,slot=spec.split(':');address=address.lower()
 if address not in s['accounts']:raise ValueError('unknown account')
 keys.setdefault(address,[]).append(int(slot,16))
values=read_slots(b.rpc,block,keys)
for address,slots in values.items():
 target=s['accounts'][address].setdefault('storage',{});existing={int(k,16):int(v,16) for k,v in target.items()}
 for k,v in slots.items():
  if int(k,16) in existing and existing[int(k,16)]!=int(v,16):raise ValueError('storage mismatch')
  target[k]=v
if b.rpc('eth_getBlockByNumber',[block,False])['hash']!=s['anchor']['hash']:raise ValueError('anchor changed')
s['rpc_calls']+=b.calls;s.setdefault('extensions',[]).append(dict(addresses=a.address,slots=a.slot,rpc_calls=b.calls))
p.write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(dict(addresses=a.address,slots=sum(map(len,values.values())),rpc_calls=b.calls)))
