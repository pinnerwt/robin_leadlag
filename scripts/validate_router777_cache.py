"""Synthetic cache-state interventions; no historical slot values inferred."""
import json,copy,subprocess,tempfile
from pathlib import Path
from bootstrap_state import mapping,word
from v3_calldata import word as getword,blob,address
from aqua_program import parse
R='0x7777857616fb37f0cfa262e9bb945e828312df17';W='0x0bd7d308f8e1639fab988df18a8011f41eacad73';U='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
source=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
txs=[r['tx'] for r in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()) if (r['tx']['to'] or '').lower()==R]
epoch=int(source['accounts'][R]['storage']['0x9'],16);version=mapping(int(U,16),11);cache=mapping(int(U,16),10)
variants=[]
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 for previous,cached in [(0,0),(epoch,(1<<256)-1)]:
  accounts=copy.deepcopy(source['accounts']);accounts[R]['storage'][version]=hex(previous);accounts[R]['storage'][cache]=hex(cached)
  balances={t:{'0x70a08231'+word(int(R,16)).hex():'0x'+word(n).hex()} for t,n in [(W,10**18),(U,10**9)]}
  seed=dict(accounts=accounts,trace_execution=True,trace_hashes=True,getters=balances)
  Path(tmp.name).write_text(json.dumps(seed))
  result=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in txs),text=True).splitlines()))
  for r in result:
   assert r['error'] is None and len(r['calls'])==1
   assert r['calls'][0]['to']=='0x111111338c5091e8440b67b168bae16a668ac0de'
   assert r['calls'][0]['data'].startswith('0xf4d2d412')
   # Formerly missing entries are overwritten before the primary call.
   writes={int(w['slot'],16):int(w['value'],16) for w in r['storage_writes'] if w['address']==R}
   if int(version,16) in writes:
    assert writes[int(version,16)]==epoch+1 and writes[int(cache,16)]==10**9
  variants.append(result)
assert [r['calls'] for r in variants[0]]==[r['calls'] for r in variants[1]]
primary=[]
for r in variants[0]:
 d=bytes.fromhex(r['calls'][0]['data'][10:]);desc=d[getword(d,0):];program=blob(desc,getword(desc,2));parse(program)
 primary.append(dict(tx=r['tx'],maker=address(getword(desc,0)),token_in=address(getword(d,1)),token_out=address(getword(d,2)),amount=getword(d,3)))
Path('reports/amm/router777-cache-validation.json').write_text(json.dumps(dict(primary=primary,variants=variants,
 caveat='Synthetic stale cache and balances. Proves observed stale-cache branch independence, not arbitrary setter reachability or historical slot values.'),indent=2)+'\n')
print('8 primary calls identical across 2 stale-cache interventions; USDG cache overwritten with supplied local balance')
