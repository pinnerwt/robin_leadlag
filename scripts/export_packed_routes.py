"""Compile startup router storage into a small, zero-RPC decoder registry."""
import argparse,json
from pathlib import Path
from bootstrap_state import mapping,hashhex
from packed_routers import ROUTER_520,ROUTER_C33
p=argparse.ArgumentParser(description=__doc__);p.add_argument('checkpoint');p.add_argument('--training',required=True);p.add_argument('--output',default='config/packed-routers.json');a=p.parse_args()
s=json.load(open(a.checkpoint));indices=set()
# Only keys observed in initialization training. Held-out unseen keys stay unknown.
for line in open(a.training):
 t=json.loads(line)
 if t['to'].lower()==ROUTER_520 and t['data'].startswith('0xb2460c48'):indices.add(int(t['data'][10:74],16)>>240)
account=s['accounts'][ROUTER_520];slots={int(k,16):int(v,16) for k,v in account['storage'].items()};routes={}
for index in sorted(indices):
 value=slots.get(int(mapping(index,2),16))
 if value is not None and value&((1<<160)-1):routes[str(index)]='0x'+(value&((1<<160)-1)).to_bytes(20,'big').hex()
code_hash=hashhex(bytes.fromhex(account['code'][2:]))
registry={'schema':1,'anchor':s['anchor']['number'],'anchor_hash':s['anchor']['hash'],'status':'attempted_call_decoder_not_execution_confirmation','routers':{ROUTER_520:{'profile':'520-b246-v1','code_hash':code_hash,'mapping_slot':2,'pool_indexes':routes}}}
registry['routers'][ROUTER_C33]={'profile':'c33-e7-v1','code_hash':hashhex(bytes.fromhex(s['accounts'][ROUTER_C33]['code'][2:]))}
Path(a.output).write_text(json.dumps(registry,indent=2)+'\n');print('exported',len(routes),'pool indexes')
