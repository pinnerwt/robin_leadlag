"""Saved upstream V3 quote; no logs or network. Bytecode transfer amount validation."""
import json,subprocess,tempfile,sys
from pathlib import Path
from bootstrap_state import mapping
from v3_state import State
POOL='0xc3c9f0171490ef0f4536fe493f3b0ebb5ee0cb5e'
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
raw={int(k,16):int(v,16) for k,v in seed['accounts'][POOL]['storage'].items()}
slot0=raw[0];sqrt=slot0&((1<<160)-1);tick=(slot0>>160)&((1<<24)-1)
if tick&(1<<23):tick-=1<<24
bitmap={};ticks={};center=(tick//10)>>8
for index in range(center-2,center+3):
 key=int(mapping(index,6),16)
 if key not in raw:continue
 bitmap[index]=raw[key]
 for bit in range(256):
  if not raw[key]>>bit&1:continue
  t=(index*256+bit)*10;k=int(mapping(t,5),16)
  if k not in raw:continue
  packed=raw[k];net=packed>>128
  if net&(1<<127):net-=1<<128
  ticks[t]=(packed&((1<<128)-1),net)
state=State(sqrt,tick,raw[4]&((1<<128)-1),500,10,bitmap,ticks)
source=json.loads(Path('reports/amm/delegated-router-funded-balance-0.json').read_text())
call=source['result']['calls'][0];d=bytes.fromhex(call['data'][10:]);amount=int.from_bytes(d[64:96],'big');limit=int.from_bytes(d[96:128],'big')
expected=state.swap(True,amount,limit)
# Root pool call retains the recipient/callback payload; sender is delegated account.
tx=dict(source['tx'],to=POOL,data=call['data'],**{'from':source['tx']['to']})
seed['trace_execution']=True
# Explicit synthetic oracle observation, isolated from curve state and fixed fee.
index=(slot0>>184)&65535;card=(slot0>>200)&65535;now=int(seed['anchor']['timestamp'],16);tx['timestamp']=now
synthetic={}
for obs,value in [(8+index,now|(1<<248)),(8+(index+1)%card,0)]:
 if obs not in raw:
  seed['accounts'][POOL]['storage'][hex(obs)]=hex(value);synthetic[hex(obs)]=hex(value)
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(seed))
 result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
assert result['error'] is None and len(result['calls'])==1
transfer=result['calls'][0];assert transfer['data'].startswith('0xa9059cbb') and int(transfer['data'][-64:],16)==-expected['amount1']
writes=[w for w in result['storage_writes'] if w['address']==POOL and int(w['slot'],16)==0]
assert int(writes[-1]['value'],16)&((1<<160)-1)==expected['sqrt']
report=dict(synthetic_observations=synthetic,anchor=seed['anchor']['hash'],state=dict(sqrt=sqrt,tick=tick,liquidity=state.liquidity,fee=500,spacing=10,bitmap=bitmap,ticks=ticks),expected=expected,result=result,caveat='Saved checkpoint curve quote and isolated pool prefix; no original historical transaction prestate or full settlement claim.')
Path('reports/amm/delegated-upstream-curve-probe.json').write_text(json.dumps(report,indent=2)+'\n')
print('coverage',len(bitmap),len(ticks),'expected',expected)
print(result['error'],[(c['to'],c['data'][:10]) for c in result['calls']])
