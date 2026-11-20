"""Compare local zero-fee curve amounts with archived V4 bytecode results."""
import json
from pathlib import Path
from v4_pool_state import load
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
cases=json.loads(Path('tests/fixtures/universal_v4_intent.json').read_text())
returns={r['tx']:r for r in json.loads(Path('reports/amm/v4-swap-return-validation.json').read_text())['records']}
state=load(seed['accounts'][MANAGER]['storage'],cases[0]['expected']);records=[]
for c in cases:
 op=c['expected'];result=state.swap(op['zero'],-op['amount'],op['limit'])
 expected=returns[c['tx']]
 # V4 deltas are from the caller's perspective, opposite V3 pool deltas.
 assert result['amount0']==-int(expected['amount0']) and result['amount1']==-int(expected['amount1']),(c['tx'],result,expected)
 records.append(dict(tx=c['tx'],result=result))
Path('reports/amm/v4-arithmetic-validation.json').write_text(json.dumps(dict(matches=len(records),records=records,
 caveat='Same archived starting state, zero-fee and synthetic zero-delta hook branch only; no continuous historical parity'),indent=2)+'\n')
Path('tests/fixtures/v4_arithmetic.json').write_text(json.dumps(dict(state=state.__dict__,cases=[dict(zero=c['expected']['zero'],amount=-c['expected']['amount'],limit=c['expected']['limit'],expected=r['result']) for c,r in zip(cases,records)]),indent=2)+'\n')
print(f'{len(records)} local curve amount matches, both directions')
