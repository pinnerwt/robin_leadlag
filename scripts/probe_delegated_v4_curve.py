"""Actual manager swap under synthetic unlock caller; settlement deliberately incomplete."""
import json,subprocess,tempfile
from pathlib import Path
from probe_routera3d_hook_fee import IMPL
from routera3d_v4 import MANAGER,HOOK
from v4_pool_state import load
from probe_delegated_callback import push
report=json.loads(Path('reports/amm/delegated-router-funded-second-output-486392238.json').read_text());swap=report['result']['calls'][0]['data'];assert swap.startswith('0xf3cd914c')
root=report['tx']['to'].lower();seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
unlock=bytes.fromhex('48c89491')+(32).to_bytes(32,'big')+(0).to_bytes(32,'big');swapraw=bytes.fromhex(swap[2:])
def invoke(data,offset):
 return b'\x61'+len(data).to_bytes(2,'big')+b'\x61'+offset.to_bytes(2,'big')+b'\x60\x00\x39'+push(0)+push(0)+push(len(data))+push(0)+push(0)+bytes.fromhex('73'+MANAGER[2:])+b'\x5a\xf1\x50\x00'
head=b'\x5f\x35'+push(224)+b'\x1c'+push(0x91dd7346)+b'\x14\x61\x00\x00\x57'
u=invoke(unlock,0);v=b'\x5b'+invoke(swapraw,0);start=len(head)+len(u)+len(v)
head=head[:-3]+(len(head)+len(u)).to_bytes(2,'big')+head[-1:]
code=head+invoke(unlock,start)+b'\x5b'+invoke(swapraw,start+len(unlock))+unlock+swapraw
seed['accounts'][root]['code']='0x'+code.hex();seed['execute_targets']=[MANAGER,HOOK,root];seed['delegate_targets']=[IMPL];seed['trace_execution']=True
# Synthetic harness calls real manager unlock, which establishes transient unlocked state.
tx=dict(report['tx'],data='0x',sequence=int(seed['anchor']['number'],16),timestamp=int(seed['anchor']['timestamp'],16))
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(seed));result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
d=bytes.fromhex(swap[10:]);words=[int.from_bytes(d[i:i+32],'big') for i in range(0,len(d),32)]
key=dict(currency0='0x'+words[0].to_bytes(20,'big').hex(),currency1='0x'+words[1].to_bytes(20,'big').hex(),fee=words[2],tick_spacing=words[3],hooks='0x'+words[4].to_bytes(20,'big').hex())
fees=[int(x['output'][-64:],16)&0x3fffff for x in result['execution_returns'] if x['selector']=='0x575e24b4' and x['result']=='Return'];assert fees and set(fees)=={40}
state=load(seed['accounts'][MANAGER]['storage'],key,effective_lp_fee=40,bitmap_words=range(-788,-784))
amount=words[6]-(1<<256);assert amount<0 and words[5]==0
expected=state.swap(False,-amount,words[7])
returned=[x for x in result['execution_returns'] if x['selector']=='0xf3cd914c' and x['result']=='Return'];assert len(returned)==1
packed=int(returned[0]['output'],16);delta0=packed>>128;delta1=packed&((1<<128)-1)
if delta1>>127:delta1-=1<<128
assert delta0==-expected['amount0'] and delta1==-expected['amount1']
slot='0xa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8'
writes=[w for w in result['storage_writes'] if w['address']==MANAGER and w['slot']==slot];assert len(writes)==1
assert int(writes[0]['value'],16)&((1<<160)-1)==expected['sqrt']
print('local curve',expected)
Path('reports/amm/delegated-v4-curve-probe.json').write_text(json.dumps(dict(expected=expected,key=key,state=state.__dict__,anchor=seed['anchor']['hash'],transaction=tx,swap=swap,result=result,caveat='Synthetic caller harness; real manager/hook swap; no funding/settlement or full root success claim.'),indent=2)+'\n')
print(result['error'],result['calls']);print([x for x in result['execution_returns'] if x['selector'] in ('0xf3cd914c','0x575e24b4')])
