"""Sequential local route simulation with explicitly synthetic initial inventory."""
import json,copy
from pathlib import Path
from v3_state import State
from read_local_router_inventory import inventory_at
from v4_v3_bridge import Bridge,plan
f=json.loads(Path('tests/fixtures/v4_arithmetic.json').read_text());d=f['state'];d['bitmap']={int(k):v for k,v in d['bitmap'].items()};d['ticks']={int(k):tuple(v) for k,v in d['ticks'].items()};v4=State(**d)
seed=json.loads(Path('captures/startup-v9-quotes.json').read_text());meta={p['pool']:p for p in seed['pools']};states={a:State.load(p) for a,p in meta.items()}
rows=[]
for row in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()):
 if (row['tx']['to'] or '').lower()!='0x204faca1764b154221e35c0d20abb3c525710498':continue
 try:r=plan(row['tx']['data'])
 except ValueError:continue
 rows.append(row['tx'])
assert len(rows)==4
route=plan(rows[0]['data']);anchor=seed['anchor']['hash']
inventory_report=json.loads(Path('reports/amm/router-inventory-checkpoint.json').read_text())
actual_inventory=inventory_at(inventory_report,'0x204faca1764b154221e35c0d20abb3c525710498',anchor,[route['v3_in'],route['v3_out']])
b=Bridge(v4,route['v4'],states,meta,actual_inventory,{t['from'].lower():True for t in rows},[anchor]*3)
before=copy.deepcopy((b.v4,b.states,b.inventory))
try:b.apply(rows[0]['data'],'0x'+'ff'*20)
except ValueError as e:assert 'flag' in str(e)
else:raise AssertionError('uninitialized sender must not pick fee branch')
assert (b.v4,b.states,b.inventory)==before
records=[b.apply(t['data'],t['from']) for t in rows]
assert all(r['v3_requested_input']==-r['v4']['amount1'] for r in records)
assert all(r['unwrapped']==-min(r['v3']['amount0'],r['v3']['amount1']) for r in records)
# Nonzero input inventory must contribute to the dependent V3 amount.
x=Bridge(v4,route['v4'],states,meta,{route['v3_in']:12345,route['v3_out']:6789},{rows[0]['from'].lower():True},[anchor]*3)
xr=x.apply(rows[0]['data'],rows[0]['from'])
assert xr['v3_requested_input']==-xr['v4']['amount1']+12345
assert xr['unwrapped']==-min(xr['v3']['amount0'],xr['v3']['amount1'])+6789
pool=records[-1]['pool'];b.states[pool].bitmap={};before=copy.deepcopy((b.v4,b.states,b.inventory))
try:b.apply(rows[0]['data'],rows[0]['from'])
except ValueError as e:failure=str(e)
else:raise AssertionError('missing downstream state should fail')
assert (b.v4,b.states,b.inventory)==before
Path('reports/amm/v4-v3-bridge-validation.json').write_text(json.dumps(dict(records=records,rollback=failure,
 caveat='Locally verified checkpoint inventory; synthetic true flags on archived state; assumed-success swaps, not historical or native-recipient parity'),indent=2)+'\n')
Path('tests/fixtures/v4_v3_routes.json').write_text(json.dumps(rows,indent=2)+'\n')
print('4 sequential two-pool commits; downstream failure rolls back V4 and inventory')
