"""Reproduce one Permit2/V3 argument match using pinned archived bytecode."""
import json,subprocess,tempfile
from pathlib import Path
from v3_calldata import word,signed
from packed_routers import decode_packed
f=json.loads(Path('tests/fixtures/universal_permit.json').read_text())
registry=json.loads(Path('config/optimistic-router-template.json').read_text())
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
p=dict(accounts=seed['accounts'],trace_execution=True,getters={})
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
    Path(tmp.name).write_text(json.dumps(p))
    first=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(f['tx']),text=True))
    assert first['error'] is None and len(first['calls'])==1
    permit=first['calls'][0]
    assert permit['to']=='0x000000000022d473030f116ddee9f6b43ac78ba3' and permit['data'].startswith('0x2b67b570')
    p['getters']={permit['to']:{permit['data']:'0x'}} # explicitly assume successful authorization
    Path(tmp.name).write_text(json.dumps(p))
    result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(f['tx']),text=True))
assert result['error'] is None and result['calls']==[f['call']]
op=decode_packed(f['tx']['to'],f['tx']['data'],registry,tracked_pools=f['pools'])[0]
call=result['calls'][0];raw=bytes.fromhex(call['data'][10:])
assert call['to']==op['pool'] and bool(word(raw,1))==op['zero'] and signed(word(raw,2))==op['amount']
row=next(r for r in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()) if r['tx']['tx']==f['tx']['tx'])
log=next(l for l in row['logs'] if l['address'].lower()==op['pool']);data=bytes.fromhex(log['data'][2:])
assert min(signed(word(data,0)),signed(word(data,1)))==op['amount']
Path('reports/amm/universal-permit-validation.json').write_text(json.dumps(dict(bytecode_pool_argument_matches=1,actual_log_output_matches=1,
 caveat='Permit authorization assumed successful; no full callback/state parity claim'),indent=2)+'\n')
print('1 bytecode pool argument match; 1 historical exact-output amount match')
