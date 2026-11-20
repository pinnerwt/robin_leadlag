"""Decode actual archived hub calls and compare their pending storage writes."""
import json
from pathlib import Path
from hub_state import HUB,AGGREGATOR,withdrawal_fields,storage_key,withdraw
seed=json.loads(Path('reports/amm/routerc9-c7-synthetic-seed.json').read_text())
initial={int(k,16):int(v,16) for k,v in seed['accounts'][HUB]['storage'].items()}
cases=[]
for row in map(json.loads,Path('reports/amm/routerc9-hub-writes.jsonl').read_text().splitlines()):
    state=dict(initial)
    calls=[c for c in row['execution_calls'] if c['to']==HUB and c['data'].startswith('0xb00bbd10')]
    writes=[w for w in row['storage_writes'] if w['address']==HUB]
    assert len(calls)==len(writes)==2
    for call,write in zip(calls,writes):
        op=withdrawal_fields(call['data'],AGGREGATOR)
        slot=int(storage_key(op['maker'],op['caller'],op['program_hash'],op['token']),16)
        assert slot==int(write['slot'],16)
        expected=withdraw(state[slot],op['amount'])
        assert expected==int(write['value'],16)
        cases.append(dict(calldata=call['data'],caller=AGGREGATOR,expected=op))
        state[slot]=expected
assert len(cases)==18
Path('tests/fixtures/hub_withdrawals.json').write_text(json.dumps(cases,indent=2)+'\n')
print('18 decoded hub pulls match archived pending storage writes; not full transaction success')
