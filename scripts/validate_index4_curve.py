"""Compare local integer curve to actual pool bytecode with synthetic settlement."""
import json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import mapping
from v3_state import State
POOL='0x7615926023bb149f36095645c2a81dc367d39750'
s=json.load(open('reports/amm/routera3d-index4-fresh-dependencies.json'));r=json.load(open('reports/amm/routera3d-index4-fresh-settlement-probe.json'))
assert s['anchor']['hash']==r['anchor']['hash']
s.update(trace_execution=True,delegate_targets=['0x1642634c8cb1c9f1b84c9a1a08534f8c3f4e89f8'])
requests=[dict(r['transactions'][0],data=data,tx=name) for name,data in [('liquidity','0x1a686502'),('spacing','0xd0c93a7c')]]
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(s));getters=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True).splitlines()))
for g in getters:
 assert g['execution_success'] and not g['calls'],g
liquidity,spacing=[int(g['output'],16) for g in getters]
raw={int(k,16):int(v,16) for k,v in s['accounts'][POOL]['storage'].items()}
sqrt=raw[6]&((1<<160)-1);tick=(raw[6]>>160)&((1<<24)-1)
if tick&(1<<23):tick-=1<<24
assert liquidity==raw[13]&((1<<128)-1)
assert spacing==(raw[12]>>176)&((1<<24)-1)
word=(tick//spacing)>>8;bitmap={word:raw[int(mapping(word,15),16)]}
cases=[]
for tx,result in zip(r['transactions'],r['results']):
 assert result['execution_success'] and not result['calls'] and not result['error']
 data=bytes.fromhex(tx['data'][10:]);words=[int.from_bytes(data[i:i+32],'big') for i in range(0,len(data),32)]
 fees=[int(x['output'],16) for x in result['execution_returns'] if x['selector']=='0xd3e6bf58'];assert len(fees)==1
 state=State(sqrt,tick,liquidity,fees[0],spacing,dict(bitmap),{})
 calculated=state.swap(bool(words[1]),words[2],words[3],True)
 out=bytes.fromhex(result['output'][2:]);deltas=[int.from_bytes(out[i:i+32],'big',signed=True) for i in (0,32)]
 writes=[x for x in result['storage_writes'] if x['address']==POOL and int(x['slot'],16)==6];last=int(writes[-1]['value'],16)
 actual_sqrt=last&((1<<160)-1);actual_tick=(last>>160)&((1<<24)-1)
 if actual_tick&(1<<23):actual_tick-=1<<24
 assert [calculated['amount0'],calculated['amount1']]==deltas
 assert (calculated['sqrt'],calculated['tick'])==(actual_sqrt,actual_tick)
 cases.append(dict(tx=tx['tx'],fee=fees[0],result=calculated,bytecode_deltas=deltas,bytecode_sqrt=actual_sqrt,bytecode_tick=actual_tick))
report=dict(anchor_hash=s['anchor']['hash'],liquidity=liquidity,spacing=spacing,getter_evidence=getters,cases=cases,caveat='Two small swaps, no initialized tick crossing; mocked transfer/payment/callback. Full router and continuous-state parity unproven.')
Path('reports/amm/routera3d-index4-curve-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='getter_evidence'},indent=2))
