"""Integration validation of shared-anchor, calldata-only two-leg transitions."""
import copy
import json
from pathlib import Path
from cc1a_state_bridge import Bridge,RejectedTransition
from cc1a_route import V3_POOL

seed=json.loads(Path('captures/startup-v9-quotes.json').read_text())
tx=next(json.loads(l)['tx'] for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if json.loads(l)['tx']['tx'].startswith('0x741ba04c'))
records=[]
with Bridge(seed,'captures/startup-v9-dependencies.json') as bridge:
    before=copy.deepcopy(bridge.states[V3_POOL])
    first=bridge.apply(tx['data']);records.append(first)
    assert bridge.states[V3_POOL]!=before
    after=copy.deepcopy(bridge.states[V3_POOL])
    try:bridge.apply(tx['data'])
    except RejectedTransition as error:
        records.append(dict(expected_rejection=str(error)))
    else:raise AssertionError('expected second identical swap to exceed remaining Metric capacity')
    assert bridge.states[V3_POOL]==after,'V3 state changed on Metric failure'
    assert bridge.valid,'deterministic candidate failure should preserve usable state'
    # Small follow-up proves the Metric worker also retained a usable committed state.
    data=bytearray.fromhex(tx['data'][2:]);data[12:21]=(10**6).to_bytes(9,'big')
    third=bridge.apply('0x'+data.hex());records.append(third)
    assert int(third['metric']['amount0'])==int(third['upstream_amount'])
    saved=copy.deepcopy(bridge.states[V3_POOL])
    bridge.worker.terminate();bridge.worker.wait(timeout=5)
    try:bridge.apply('0x'+data.hex())
    except (BrokenPipeError,RuntimeError):pass
    else:raise AssertionError('dead worker must invalidate bridge')
    assert not bridge.valid and bridge.states[V3_POOL]==saved

report=dict(purpose='Three sequential local route experiments, no historical parity or transaction settlement claim',
            anchor_hash=seed['anchor']['hash'],checks=['both legs commit','Metric failure rolls back V3',
            'small subsequent route remains usable','unsynchronized upstream account barrier active','worker loss invalidates bridge'],records=records)
Path('reports/amm/routercc1-bridge-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('two route commits and intervening rollback verified')
