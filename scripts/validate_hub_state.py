"""Validate initialization keys and pending withdrawal writes against bytecode."""
import json
from pathlib import Path
from hub_state import HUB,primary_keys,storage_key,withdraw
from v3_calldata import word,address
seed=json.loads(Path('reports/amm/routerc9-c7-synthetic-seed.json').read_text())
initial={int(k,16):int(v,16) for k,v in seed['accounts'][HUB]['storage'].items()}
fixtures=[];count=0
for line in Path('reports/amm/routerc9-hub-writes.jsonl').read_text().splitlines():
    row=json.loads(line)
    primary=next(c for c in row['execution_calls'] if c['data'].startswith('0xf4d2d412'))
    keys=primary_keys(primary['data'])
    observed={int(r['slot'],16) for r in row['storage_reads'] if r['address']==HUB}
    assert observed=={int(k,16) for k in keys['token_slots'].values()}
    calls=[c for c in row['execution_calls'] if c['to']==HUB and c['data'].startswith('0xb00bbd10')]
    writes=[w for w in row['storage_writes'] if w['address']==HUB]
    assert len(calls)==len(writes)
    state=dict(initial);cases=[]
    for call,actual in zip(calls,writes):
        data=bytes.fromhex(call['data'][10:])
        slot=storage_key(address(word(data,0)),keys['caller'],'0x'+format(word(data,1),'064x'),address(word(data,2)))
        old=state[int(slot,16)];new=withdraw(old,word(data,3))
        assert int(slot,16)==int(actual['slot'],16) and new==int(actual['value'],16)
        state[int(slot,16)]=new;count+=1
        cases.append(dict(old=hex(old),amount=word(data,3),expected=hex(new)))
    fixtures.append(dict(primary=primary['data'],keys=keys,withdrawals=cases))
Path('tests/fixtures/hub_state.json').write_text(json.dumps(fixtures,indent=2)+'\n')
Path('reports/amm/hub-state-validation.json').write_text(json.dumps(dict(transactions=len(fixtures),pending_write_matches=count,
 caveat='SSTORE attempts before unresolved callbacks; not committed transaction parity or complete hub reducer'),indent=2)+'\n')
print(f'{len(fixtures)} key sets and {count} pending writes match')
