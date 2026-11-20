"""Compose saved curve outputs; validate downstream pool transfer with actual code."""
import json,subprocess,tempfile
from pathlib import Path
from v3_state import State,MIN_SQRT
up=json.loads(Path('reports/amm/delegated-upstream-curve-probe.json').read_text())
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
quotes=json.loads(Path('captures/startup-v9-quotes.json').read_text())
assert up['anchor']==seed['anchor']['hash']==quotes['anchor']['hash']
pool='0xc61284332117c3fb23a2a56cceffd07f7af60029'
meta=next(p for p in quotes['pools'] if p['pool']==pool)
amount=-up['expected']['amount1'];expected=State.load(meta).swap(True,amount,MIN_SQRT+1)
source=json.loads(Path('reports/amm/delegated-router-funded-output-1000000000000000000.json').read_text())
call=source['result']['calls'][0];assert call['to']==pool
data=bytearray.fromhex(call['data'][10:]);data[64:96]=amount.to_bytes(32,'big')
tx=dict(source['tx'],to=pool,data='0x128acb08'+data.hex(),**{'from':source['tx']['to']})
now=int(seed['anchor']['timestamp'],16);tx['timestamp']=now;seed['trace_execution']=True
storage=seed['accounts'][pool]['storage'];raw={int(k,16):int(v,16) for k,v in storage.items()};slot=raw[0]
index=(slot>>184)&65535;card=(slot>>200)&65535;synthetic={}
for obs,value in [(8+index,now|(1<<248)),(8+(index+1)%card,0)]:
 if obs not in raw:storage[hex(obs)]=hex(value);synthetic[hex(obs)]=hex(value)
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(seed))
 result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
report=dict(anchor=up['anchor'],input_amount=amount,expected=expected,result=result,synthetic_observations=synthetic,caveat='Two isolated saved-state curves; assumes first output credited in full. Does not prove router branch selection, token accounting or full historical execution.')
Path('reports/amm/delegated-two-pool-curve-probe.json').write_text(json.dumps(report,indent=2)+'\n')
print(expected);print(result['error'],[(c['to'],c['data'][:10]) for c in result['calls']])
assert result['error'] is None and len(result['calls'])==1
transfer=result['calls'][0];assert transfer['data'].startswith('0xa9059cbb') and int(transfer['data'][-64:],16)==-expected['amount1']
writes=[w for w in result['storage_writes'] if w['address']==pool and int(w['slot'],16)==0]
assert int(writes[-1]['value'],16)&((1<<160)-1)==expected['sqrt']
