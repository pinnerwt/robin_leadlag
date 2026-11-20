"""Check callback extraction against bytecode prefix and actual swap quantities."""
import json
from pathlib import Path
from c9_router import C9,V3_ROUTER
from packed_routers import decode_packed
from v3_calldata import decode,word,signed
registry=json.loads(Path('config/optimistic-router-template.json').read_text())
pools={p['pool']:p for p in json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']}
prefix={r['tx']:r for r in map(json.loads,Path('reports/amm/routerc9-callback-prefix.jsonl').read_text().splitlines())}
fixtures=[]
for row in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()):
    tx=row['tx']
    if (tx['to'] or '').lower()!=C9 or not tx['data'].startswith('0xbad401db'):continue
    ops=decode_packed(C9,tx['data'],registry,tracked_pools=pools)
    trace=prefix[tx['tx']]
    assert trace['error'] is None and len(trace['calls'])==1
    call=trace['calls'][0];assert call['to']==V3_ROUTER
    expected=decode(call['to'],call['data'],pools,{V3_ROUTER})
    assert len(ops)==len(expected)==1
    assert all(ops[0][k]==v for k,v in expected[0].items())
    logs=[l for l in row['logs'] if l['address'].lower()==ops[0]['pool']]
    assert len(logs)==1
    raw=bytes.fromhex(logs[0]['data'][2:]);x,y=signed(word(raw,0)),signed(word(raw,1))
    assert (x>0)==ops[0]['zero'] and min(x,y)==ops[0]['amount']
    fixtures.append(dict(tx=tx,expected=ops,call=call))
assert len(fixtures)==5
Path('tests/fixtures/routerc9.json').write_text(json.dumps(dict(pools={a:dict(tokens=p['tokens'],fee=p['fee']) for a,p in pools.items()},cases=fixtures),indent=2)+'\n')
Path('reports/amm/routerc9-validation.json').write_text(json.dumps(dict(bytecode_callback_matches=5,log_exact_output_matches=5,upstream_settlement_unresolved=True,
 caveat='Archived bytecode with synthetic token balance/approval responses; no full execution or state parity'),indent=2)+'\n')
print('5 callback argument matches; 5 real swap exact-output matches; upstream unresolved')
