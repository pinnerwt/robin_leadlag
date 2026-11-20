"""Validate fixed-input Universal V3 then native settlement prefix."""
import json,subprocess,tempfile
from pathlib import Path
from packed_routers import decode_packed
from v3_calldata import word,signed
row=next(r for r in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()) if r['tx']['tx'].startswith('0xfeaea7dc39'))
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(dict(accounts=seed['accounts'],trace_execution=True)))
 result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(row['tx']),text=True))
assert result['error'] is None and len(result['calls'])==1
pools=json.loads(Path('tests/fixtures/universal_permit.json').read_text())['pools']
registry=json.loads(Path('config/optimistic-router-template.json').read_text())
ops=decode_packed(row['tx']['to'],row['tx']['data'],registry,tracked_pools=pools);assert len(ops)==1
op=ops[0];call=result['calls'][0];d=bytes.fromhex(call['data'][10:])
assert call['data'].startswith('0x128acb08') and call['to']==op['pool']
assert bool(word(d,1))==op['zero'] and signed(word(d,2))==op['amount']
log=next(l for l in row['logs'] if l['address'].lower()==op['pool']);d=bytes.fromhex(log['data'][2:])
assert max(signed(word(d,0)),signed(word(d,1)))==op['amount']
Path('tests/fixtures/universal_input.json').write_text(json.dumps(dict(tx=row['tx'],expected=ops,pools=pools),indent=2)+'\n')
Path('reports/amm/universal-input-validation.json').write_text(json.dumps(dict(bytecode_pool_argument_matches=1,log_input_matches=1,result=result,
 caveat='Native settlement execution unresolved; no full transaction parity'),indent=2)+'\n')
print('1 fixed-input bytecode argument match; 1 historical swap input match')
