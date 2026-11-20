"""Compare sell intent and independent integer curve with manager bytecode."""
import json
from pathlib import Path
from routera3d_v4 import forward_intent
from v3_calldata import word,signed
from v3_state import State
fixture=json.loads(Path('tests/fixtures/routera3d_v4_math.json').read_text())
records=[]
for c in json.loads(Path('reports/amm/routera3d-v4-sell-probe.json').read_text())['cases']:
    op=forward_intent(c['transaction']['data'],0,10**18,hook_fee_ppm=160)
    call=next(x for x in c['result']['execution_calls'] if x['data'].startswith('0xf3cd914c'))
    raw=bytes.fromhex(call['data'][10:])
    assert word(raw,5)==1 and signed(word(raw,6))==op['amount'] and word(raw,7)==op['limit']
    state=State.load(fixture['state']);state.fee=160
    result=state.swap(True,-op['amount'],op['limit'])
    returned=next(x for x in c['result']['execution_returns'] if x['selector']=='0xf3cd914c')
    assert returned['result']=='Return'
    packed=int(returned['output'],16);d0=(packed>>128)-(1<<128);d1=packed&((1<<128)-1)
    assert result['amount0']==-d0 and result['amount1']==-d1
    records.append(dict(calldata=c['transaction']['data'],intent=op,result=result))
Path('tests/fixtures/routera3d_v4_sell.json').write_text(json.dumps(dict(state=fixture['state'],cases=records),indent=2)+'\n')
Path('reports/amm/routera3d-v4-sell-validation.json').write_text(json.dumps(dict(matches=len(records),
    caveat='Actual router/manager swap arguments and internal returned deltas; synthetic parent inventory. Settlement interrupted at token transfer; not committed state or historical parity.'),indent=2)+'\n')
print(f'{len(records)} sell sizes/limits and local curve amounts match')
