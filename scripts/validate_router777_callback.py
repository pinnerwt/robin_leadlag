"""Compare callback inputs to local Aqua output and actual pool call arguments."""
import json
from pathlib import Path
from router777_plan import plan,bind_callback
from hub_state import primary_keys,HUB,MASK248
from aqua_program import quote_exact_input
from v3_calldata import word,blob,signed
cases=json.loads(Path('tests/fixtures/router777_plan.json').read_text())
traces=json.loads(Path('reports/amm/router777-sequence-prefix.json').read_text())
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
storage={int(k,16):int(v,16) for k,v in seed['accounts'][HUB]['storage'].items()}
pools=json.loads(Path('tests/fixtures/universal_permit.json').read_text())['pools']
fixtures=[]
for case,trace in zip(cases,traces):
 r=plan(case['calldata']);keys=primary_keys(r['primary'])['token_slots']
 d=bytes.fromhex(r['primary'][10:]);desc=d[word(d,0):];program=blob(desc,word(desc,2))
 q=quote_exact_input(program,r['token_in'],r['token_out'],storage[int(keys[r['token_in']],16)]&MASK248,
                    storage[int(keys[r['token_out']],16)]&MASK248,r['amount'])
 op=bind_callback(r,q['amount_out'],pools)
 assert trace['error'] is None and len(trace['calls'])==1
 call=trace['calls'][0];b=bytes.fromhex(call['data'][10:])
 assert call['to']==op['pool'] and call['data'].startswith('0x128acb08')
 assert bool(word(b,1))==op['zero'] and signed(word(b,2))==op['amount'] and word(b,3)==op['limit']
 fixtures.append(dict(calldata=case['calldata'],aqua_output=q['amount_out'],expected=op))
assert len(fixtures)==8
Path('tests/fixtures/router777_callback.json').write_text(json.dumps(dict(pools=pools,cases=fixtures),indent=2)+'\n')
Path('reports/amm/router777-callback-validation.json').write_text(json.dumps(dict(matches=8,
 caveat='Archived Aqua pricing and synthetic token balance transitions; no historical/full-settlement parity'),indent=2)+'\n')
print('8 V3 callback arguments match locally priced Aqua output, including both directions')
