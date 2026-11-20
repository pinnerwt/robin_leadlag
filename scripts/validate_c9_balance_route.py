"""C7 callback bytecode parity with explicit synthetic callback balances."""
import json
from pathlib import Path
from c9_balance_route import plan,resolve_callback
from c9_router import C9,V3_ROUTER
from v3_calldata import decode
pools=json.loads(Path('tests/fixtures/routerc9.json').read_text())['pools']
prefix={r['tx']:r for r in map(json.loads,Path('reports/amm/routerc9-c7-positive-prefix.jsonl').read_text().splitlines())}
cases=[]
for row in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()):
    tx=row['tx']
    if (tx['to'] or '').lower()!=C9 or not tx['data'].startswith('0xc7e280dd'):continue
    route=plan(tx['data'])
    calls=prefix[tx['tx']]['calls']
    assert len(calls)==1 and calls[0]['to']==V3_ROUTER
    expected=decode(V3_ROUTER,calls[0]['data'],pools,{V3_ROUTER})
    assert resolve_callback(route,10**18,pools)==expected
    cases.append(dict(calldata=tx['data'],route=route,callback_balance=10**18,expected=expected))
assert len(cases)==4
Path('tests/fixtures/c9_balance_route.json').write_text(json.dumps(dict(pools=pools,cases=cases),indent=2)+'\n')
report=dict(bytecode_callback_matches=len(cases),synthetic_callback_balance=10**18,
            live_registered=False,state_complete=False,
            caveat='Known callback balance, not historical swap or continuous Aqua settlement parity')
Path('reports/amm/c9-balance-route-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
