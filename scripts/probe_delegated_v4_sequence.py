"""Two real manager swaps in one synthetic unlock callback; no settlement claim."""
import json,subprocess,tempfile
from pathlib import Path
from probe_delegated_callback import push
from probe_routera3d_hook_fee import IMPL
from routera3d_v4 import MANAGER,HOOK
first=json.loads(Path('reports/amm/delegated-v4-curve-probe.json').read_text());local=json.loads(Path('reports/amm/delegated-local-relaxed-preview.json').read_text());seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
assert first['anchor']==local['anchor']==seed['anchor']['hash']
tx=first['transaction'];root=tx['to'].lower();swaps=[bytes.fromhex(first['swap'][2:])]
b=bytearray(swaps[0]);amount=local['result']['state']['executed'][1]['fills'][-1]['amount1'];b[4+6*32:4+7*32]=((-amount)%(1<<256)).to_bytes(32,'big');swaps.append(bytes(b))
unlock=bytes.fromhex('48c89491')+(32).to_bytes(32,'big')+bytes(32)
def invoke(data,offset,stop=True):
 return b'\x61'+len(data).to_bytes(2,'big')+b'\x61'+offset.to_bytes(2,'big')+b'\x60\x00\x39'+push(0)*2+push(len(data))+push(0)*2+bytes.fromhex('73'+MANAGER[2:])+b'\x5a\xf1\x50'+(b'\x00' if stop else b'')
head=b'\x5f\x35'+push(224)+b'\x1c'+push(0x91dd7346)+b'\x14\x61\x00\x00\x57'
u=invoke(unlock,0);v=b'\x5b'+invoke(swaps[0],0,False)+invoke(swaps[1],0);start=len(head)+len(u)+len(v)
head=head[:-3]+(len(head)+len(u)).to_bytes(2,'big')+head[-1:]
code=head+invoke(unlock,start)+b'\x5b'+invoke(swaps[0],start+len(unlock),False)+invoke(swaps[1],start+len(unlock)+len(swaps[0]))+unlock+b''.join(swaps)
seed['accounts'][root]['code']='0x'+code.hex();seed.update(execute_targets=[root,MANAGER,HOOK],delegate_targets=[IMPL],trace_execution=True)
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(seed));result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
returns=[r for r in result['execution_returns'] if r['selector']=='0xf3cd914c' and r['result']=='Return'];assert result['error'] is None and len(returns)==2
for actual,expected in zip(returns,local['result']['state']['executed']):
 packed=int(actual['output'],16);self_input=packed&((1<<128)-1);self_input-=1<<128 if self_input>>127 else 0
 assert packed>>128==expected['output_native'] and self_input==-expected['fills'][-1]['amount1']
fees=[int(r['output'][-64:],16)&0x3fffff for r in result['execution_returns'] if r['selector']=='0x575e24b4' and r['depth']==4 and r['result']=='Return'];assert fees==[40,90],fees
Path('reports/amm/delegated-v4-sequence-probe.json').write_text(json.dumps(dict(anchor=first['anchor'],fees=fees,result=result,caveat='Real sequential manager/hook execution in synthetic callback. Outer unlock not settled; local strategy success and relaxed conditions assumed.'),indent=2)+'\n')
print('two sequential swaps match, fees',fees)
