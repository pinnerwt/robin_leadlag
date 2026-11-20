"""Five archived calldata routes on local state, synthetic inventory/flags."""
import json,copy
from pathlib import Path
from v3_state import State
from read_local_router_inventory import inventory_at
from universal_roundtrip_bridge import Bridge
from v4_v3_bridge import WETH
rows=json.loads(Path('tests/fixtures/universal_roundtrip.json').read_text())
d=json.loads(Path('tests/fixtures/v4_arithmetic.json').read_text())['state'];d['bitmap']={int(k):v for k,v in d['bitmap'].items()};d['ticks']={int(k):tuple(v) for k,v in d['ticks'].items()}
seed=json.loads(Path('captures/startup-v9-quotes.json').read_text());meta={p['pool']:p for p in seed['pools']};states={a:State.load(p) for a,p in meta.items()};key=rows[0]['plan']['v4'];usd=key['currency1'];anchor=seed['anchor']['hash']
inventory_report=json.loads(Path('reports/amm/router-inventory-checkpoint.json').read_text())
actual_inventory=inventory_at(inventory_report,'0x204faca1764b154221e35c0d20abb3c525710498',anchor,[usd,WETH])
b=Bridge(State(**d),key,states,meta,actual_inventory,{r['tx']['from'].lower():True for r in rows},[anchor]*3)
records=[]
for row in rows:
 t=row['tx'];before=copy.deepcopy((b.states,b.v4,b.inventory))
 try:
  out=b.apply(t['data'],t['from'],int(t['value'],16))
 except ValueError as e:
  assert (b.states,b.v4,b.inventory)==before
  records.append(dict(tx=t['tx'],rejection=str(e)));continue
 # Each final input is first-leg output minus actual V4 input (zero prior USDG).
 assert out['final_requested']==-min(out['first_v3']['amount0'],out['first_v3']['amount1'])-out['v4']['amount1']
 records.append(dict(tx=t['tx'],result=out))
funded=[]
for row in rows:
 t=row['tx'];inventory=10**9
 candidate=Bridge(State(**d),key,states,meta,{usd:inventory,WETH:0},{t['from'].lower():True},[anchor]*3)
 out=candidate.apply(t['data'],t['from'],int(t['value'],16))
 assert out['final_requested']==inventory-min(out['first_v3']['amount0'],out['first_v3']['amount1'])-out['v4']['amount1']
 # Independent replay of both V3 legs demonstrates state reuse; old-state last quote differs.
 v3=copy.deepcopy(states[out['pool']]);zero=meta[out['pool']]['tokens'][0]==WETH
 v3.swap(zero,int(t['value'],16),None,True)
 assert v3.swap(not zero,out['final_requested'],None,True)==out['last_v3']
 assert states[out['pool']].swap(not zero,out['final_requested'])!=out['last_v3']
 funded.append(dict(tx=t['tx'],synthetic_initial_usdg=inventory,result=out))
assert len(funded)==5
Path('reports/amm/universal-roundtrip-bridge-validation.json').write_text(json.dumps(dict(records=records,funded=funded,caveat='Primary runs use locally verified inventory and synthetic true flags; funded runs use synthetic USDG. Not historical execution or native callback parity.'),indent=2)+'\n')
print(json.dumps(dict(zero_inventory_commits=sum('result' in r for r in records),funded_commits=len(funded),rejections=[r['rejection'] for r in records if 'rejection' in r])))
