"""Compare pricing math with actual archived router's token-transfer arguments."""
import json
from pathlib import Path
from hub_state import primary_keys,HUB,MASK248
from v3_calldata import word,blob,address
from aqua_program import quote_exact_input
seed=json.loads(Path('reports/amm/routerc9-c7-synthetic-seed.json').read_text())
state={int(k,16):int(v,16) for k,v in seed['accounts'][HUB]['storage'].items()}
fixtures=[]
for line in Path('reports/amm/routerc9-hub-writes.jsonl').read_text().splitlines():
    row=json.loads(line);primary=next(c for c in row['execution_calls'] if c['data'].startswith('0xf4d2d412'))
    data=bytes.fromhex(primary['data'][10:]);desc=data[word(data,0):];program=blob(desc,word(desc,2))
    keys=primary_keys(primary['data']);tin,tout=address(word(data,1)),address(word(data,2))
    bi,bo=[state[int(keys['token_slots'][t],16)]&MASK248 for t in (tin,tout)]
    result=quote_exact_input(program,tin,tout,bi,bo,word(data,3))
    calls=[c for c in row['execution_calls'] if c['to']==HUB and c['data'].startswith('0xb00bbd10')]
    amounts={address(word(bytes.fromhex(c['data'][10:]),2)):word(bytes.fromhex(c['data'][10:]),3) for c in calls}
    assert result['amount_out']==amounts[tout],(row['tx'],result['amount_out'],amounts[tout])
    assert result['protocol_fee']==amounts[tin]
    fixtures.append(dict(program=program.hex(),token_in=tin,token_out=tout,balance_in=bi,balance_out=bo,
                         amount=word(data,3),expected=result))
# Additional independent bytecode runs changed each hub field by +/-1%.
base=fixtures[0]
first_trace=json.loads(Path('reports/amm/routerc9-hub-writes.jsonl').read_text().splitlines()[0])
first_payload=next(c['data'] for c in first_trace['execution_calls'] if c['data'].startswith('0xf4d2d412'))
first_keys=primary_keys(first_payload)['token_slots']
for case in json.loads(Path('reports/amm/routerc9-c7-storage-probe.json').read_text())['cases']:
    inputs={k:base[k] for k in ('token_in','token_out','balance_in','balance_out','amount')}
    field='balance_in' if int(case['slot'],16)==int(first_keys[base['token_in']],16) else 'balance_out'
    inputs[field]=int(case['new'],16)&MASK248
    result=quote_exact_input(bytes.fromhex(base['program']),**inputs)
    assert result['amount_out']==case['transfers'][0]
    fee_calls=[bytes.fromhex(c['data'][10:]) for c in case['result']['execution_calls'] if c['to']==HUB and c['data'].startswith('0xb00bbd10')]
    fee=next(word(d,3) for d in fee_calls if address(word(d,2))==base['token_in'])
    assert result['protocol_fee']==fee
    fixtures.append(dict(program=base['program'],**inputs,expected=result))
Path('tests/fixtures/aqua_program.json').write_text(json.dumps(fixtures,indent=2)+'\n')
Path('reports/amm/aqua-program-validation.json').write_text(json.dumps(dict(cases=len(fixtures),output_and_fee_matches=len(fixtures),
 source_reference='https://github.com/1inch/swap-vm/tree/363e3fea1c9df7dc3df6762c3cc40dd57fc4ced5',
 caveat='Math matches archived bytecode with archived hub state; not original transaction-state parity or full source/compiler hash equivalence'),indent=2)+'\n')
print(f'{len(fixtures)} output and protocol-fee amounts match bytecode, both token directions plus hub-state interventions')
