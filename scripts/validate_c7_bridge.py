"""Sequential C7 candidate commits and failure rollback on archived checkpoints."""
import copy,json
from pathlib import Path
from c7_state_bridge import Bridge
from c9_balance_route import plan
seed=json.loads(Path('captures/startup-v9-quotes.json').read_text())
cases=json.loads(Path('tests/fixtures/c7_settlement.json').read_text())
c=cases[0];route=plan(c['calldata'])
aqua=dict(anchor_hash=seed['anchor']['hash'],strategies=[dict(maker=route['maker'],program=route['program'],
 balances={route['token_in']:c['old_in'],route['token_out']:c['old_out']})],router_inventory={route['token_out']:0})
b=Bridge(seed,aqua)
first=b.apply(c['calldata']);second=b.apply(c['calldata'])
assert first['aqua']['amount_out']>second['aqua']['amount_out']
assert first['router_output_inventory']==second['router_output_inventory']==0
# Missing tick coverage must roll back both allocation and inventory candidates.
pool=first['pool'];saved=copy.deepcopy((b.states,b.allocations,b.inventory));b.states[pool].bitmap={}
failed_before=copy.deepcopy((b.states,b.allocations,b.inventory))
try:b.apply(c['calldata'])
except ValueError as error:failure=str(error)
else:raise AssertionError('missing bitmap should fail')
assert (b.states,b.allocations,b.inventory)==failed_before
b.states=saved[0]
third=b.apply(c['calldata'])
assert third['aqua']['amount_out']<second['aqua']['amount_out']
report=dict(anchor_hash=seed['anchor']['hash'],records=[first,second,third],rollback_error=failure,
 caveat='Historical calldata on one archived checkpoint; synthetic initial router inventory zero. Not historical parity or live integration.')
Path('reports/amm/c7-bridge-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('3 sequential Aqua/V3 commits; missing V3 state rolls back allocations and router inventory')
