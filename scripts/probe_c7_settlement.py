"""Validate C7 Aqua settlement against bytecode with explicit synthetic funding.

V3 and token transfers are stubbed. Root minimum profit is zeroed, because
constant balanceOf stubs cannot represent the profit. No live RPC or submission.
"""
import copy,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import word
from c9_balance_route import plan
from aqua_program import parse
from hub_state import HUB,primary_keys,withdraw,deposit
seed=json.loads(Path('reports/amm/routerc9-c7-synthetic-seed.json').read_text())
prefix={r['tx']:r for r in map(json.loads,Path('reports/amm/routerc9-c7-positive-prefix.jsonl').read_text().splitlines())}
fixtures=[]
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 for row in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()):
    tx=row['tx']
    if tx['tx'] not in prefix or not tx['data'].startswith('0xc7e280dd'):continue
    route=plan(tx['data']);s=copy.deepcopy(seed)
    cb=prefix[tx['tx']]['calls'][0]
    s['getters'].setdefault(cb['to'],{})[cb['data']]='0x'+word(route['amount']+1000000).hex()
    synthetic=dict(tx);raw=bytearray.fromhex(tx['data'][2:]);raw[196:228]=word(0);synthetic['data']='0x'+raw.hex()
    for attempt in range(8):
        Path(tmp.name).write_text(json.dumps(s))
        result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(synthetic),text=True))
        assert result['error'] is None,result['error']
        if not result['calls']:break
        assert len(result['calls'])==1
        call=result['calls'][0]
        assert call['to'] in (route['token_in'],route['token_out'])
        assert call['data'][2:10] in ('095ea7b3','23b872dd')
        s['getters'][call['to']][call['data']]='0x'+word(1).hex()
    assert result['execution_success'],result['output']
    keys=primary_keys(route['primary'])['token_slots']
    storage={int(k,16):int(v,16) for k,v in seed['accounts'][HUB]['storage'].items()}
    old_in,old_out=[storage[int(keys[t],16)] for t in (route['token_in'],route['token_out'])]
    writes=[w for w in result['storage_writes'] if w['address']==HUB]
    assert len(writes)==3
    assert int(writes[0]['slot'],16)==int(keys[route['token_in']],16)
    assert int(writes[1]['slot'],16)==int(keys[route['token_out']],16)
    fee=route['amount']*parse(bytes.fromhex(route['program']))['protocol_fee']//10**9
    expected_in=deposit(withdraw(old_in,fee),route['amount'])
    assert int(writes[0]['value'],16)==withdraw(old_in,fee)
    assert int(writes[2]['slot'],16)==int(keys[route['token_in']],16)
    assert int(writes[2]['value'],16)==expected_in
    fixtures.append(dict(calldata=tx['data'],old_in=str(old_in),old_out=str(old_out),
                         new_in=str(expected_in),new_out=str(int(writes[1]['value'],16)),result=result))
assert len(fixtures)==4
Path('reports/amm/c7-settlement-validation.json').write_text(json.dumps(dict(
 caveat='Synthetic successful funding, stubbed V3 and constant balances; root minimum profit zeroed. Not historical execution parity.',
 cases=fixtures),indent=2)+'\n')
print('4 successful synthetic executions: Aqua input credits full amount, protocol fee debited separately')
