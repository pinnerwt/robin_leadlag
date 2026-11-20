"""Require identical quotes/transitions from scoped versus full local checkpoints."""
import json
import time
from pathlib import Path
from cc1a_state_bridge import Bridge
seed=json.loads(Path('captures/startup-v9-quotes.json').read_text())
tx=next(json.loads(l)['tx'] for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if json.loads(l)['tx']['tx'].startswith('0x741ba04c'))
outputs=[];timings=[]
for scope in (None,'config/metric-weth-research-scope.json'):
    with Bridge(seed,'captures/startup-v9-dependencies.json',scope=scope) as bridge:
        bridge.quotes(['0.02']) # warm worker/load outside latency sample
        start=time.perf_counter_ns();quotes=bridge.quotes(['0.02','0.1']);timings.append(time.perf_counter_ns()-start)
        route=bridge.apply(tx['data'])
        route['metric']['storage_changes'].sort(key=lambda c:(c['address'],c['slot']))
        outputs.append(dict(quotes=quotes,route=route))
assert outputs[0]==outputs[1],'scoped checkpoint changed outputs or storage writes'
report=dict(parity=True,full_wall_ns=timings[0],scoped_wall_ns=timings[1],
            measurement='single warm two-size bid/ask batch, includes Python IPC; not p90',
            scoped_accounts=json.loads(Path('config/metric-weth-research-scope.json').read_text())['accounts'])
Path('reports/amm/metric-scope-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(report)
