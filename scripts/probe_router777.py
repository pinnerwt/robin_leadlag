"""Read-only local 777 prefix; explicit synthetic inventory, no state commit."""
import json,subprocess,tempfile
from pathlib import Path
from v3_calldata import word,blob,address
from aqua_program import parse
ROUTER='0x7777857616fb37f0cfa262e9bb945e828312df17'
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73';USDG='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
txs=[r['tx'] for r in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()) if (r['tx']['to'] or '').lower()==ROUTER]
p=dict(accounts=seed['accounts'],trace_execution=True,trace_hashes=True,getters={})
results=[]
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 for phase in range(3):
  Path(tmp.name).write_text(json.dumps(p))
  output=subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in txs),text=True)
  rows=list(map(json.loads,output.splitlines()));results.append(rows)
  if phase==2:break
  for r in rows:
   for c in r['calls']:
    assert c['data'].startswith('0x70a08231') and c['to'] in (WETH,USDG)
    balance=10**18 if c['to']==WETH else 10**9
    p['getters'].setdefault(c['to'],{})[c['data']]='0x'+balance.to_bytes(32,'big').hex()
primary=[]
reference=json.loads(Path('tests/fixtures/aqua_program.json').read_text())[0]['program']
for row in results[-1]:
 if row['error']:continue
 assert len(row['calls'])==1
 c=row['calls'][0];assert c['to']=='0x111111338c5091e8440b67b168bae16a668ac0de' and c['data'].startswith('0xf4d2d412')
 d=bytes.fromhex(c['data'][10:]);desc=d[word(d,0):];program=blob(desc,word(desc,2));parse(program)
 assert program.hex()==reference
 primary.append(dict(tx=row['tx'],maker=address(word(desc,0)),token_in=address(word(d,1)),token_out=address(word(d,2)),amount=word(d,3),program=program.hex()))
assert len(primary)==3
Path('reports/amm/router777-dependency-validation.json').write_text(json.dumps(dict(primary=primary,phases=results,
 caveat='Synthetic balance responses to reveal routing; not decoder completeness or actual inventory'),indent=2)+'\n')
print('3 primary calls share the verified C9 Aqua program; 5 other routes still require token-indexed slot11 state')
