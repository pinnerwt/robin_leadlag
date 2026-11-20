"""Alternate C7 and 777 on one local allocation/V3 book, no logs or RPC."""
import copy,json
from pathlib import Path
from c7_state_bridge import Bridge,identity
from c9_balance_route import plan
from router777_plan import allocation_candidate
seed=json.loads(Path('captures/startup-v9-quotes.json').read_text())
c7=json.loads(Path('tests/fixtures/c7_settlement.json').read_text())[0]
c777=json.loads(Path('tests/fixtures/router777_plan.json').read_text())[0]
r=plan(c7['calldata']);key=identity(r)
aqua=dict(anchor_hash=seed['anchor']['hash'],strategies=[dict(maker=r['maker'],program=r['program'],
 balances={r['token_in']:c7['old_in'],r['token_out']:c7['old_out']})],router_inventory={r['token_out']:0})
b=Bridge(seed,aqua)
first=b.apply_transaction('0xc9a1dcff54632b408f2b0e048d8b7d3261697144',c7['calldata'])
pi,po=[b.allocations[key][t] for t in (r['token_in'],r['token_out'])]
expected=allocation_candidate(c777['calldata'],pi,po,b.meta)
stale=allocation_candidate(c777['calldata'],int(c7['old_in']),int(c7['old_out']),b.meta)
assert expected['quote']['amount_out']!=stale['quote']['amount_out']
inventory=copy.deepcopy(b.inventory)
second=b.apply_transaction('0x7777857616fb37f0cfa262e9bb945e828312df17',c777['calldata'])
assert second['aqua']==expected['quote'] and b.inventory==inventory
assert b.allocations[key][r['token_in']]==expected['allocation_in']
third=b.apply(c7['calldata'])
assert third['aqua']['amount_out']<first['aqua']['amount_out']
pool=second['pool'];good=copy.deepcopy(b.states[pool]);b.states[pool].bitmap={}
before=copy.deepcopy((b.states,b.allocations,b.inventory))
try:b.apply_router777(c777['calldata'])
except ValueError as error:failure=str(error)
else:raise AssertionError('missing pool state must fail')
assert (b.states,b.allocations,b.inventory)==before
b.states[pool]=good
fourth=b.apply_router777(c777['calldata'])
Path('reports/amm/shared-aqua-bridge-validation.json').write_text(json.dumps(dict(records=[first,second,third,fourth],rollback=failure,
 caveat='Alternating archived calldata on one starting snapshot, successful-transaction policy. Not historical parity; minimum-output diagnostics retained.'),indent=2)+'\n')
print('C7 -> 777 -> C7 -> 777 share changed allocations and V3 state; failed 777 rolls back both')
