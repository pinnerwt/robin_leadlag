"""Offline saved-code prefix experiment. Fixed-block getters are not historical prestate."""
import json,subprocess,tempfile
from pathlib import Path
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
quotes=json.loads(Path('captures/startup-v9-quotes.json').read_text())
assert seed['anchor']['hash']==quotes['anchor']['hash']
seed['trace_execution']=True
seed['getters']={}
for p in quotes['pools']:
 seed['getters'][p['pool']]={
  '0x0dfe1681':'0x'+int(p['tokens'][0],16).to_bytes(32,'big').hex(),
  '0xd21220a7':'0x'+int(p['tokens'][1],16).to_bytes(32,'big').hex(),
  '0x3850c7bd':'0x'+int(p['sqrt']).to_bytes(32,'big').hex()}
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(seed))
 result=subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=Path('reports/amm/delegated-router-txs.jsonl').read_text(),text=True)
Path('reports/amm/delegated-router-getter-prefix.jsonl').write_text(result)
for r in map(json.loads,result.splitlines()):
 print(r['tx'][:12],r['error'],[(c['to'],c['data'][:10]) for c in r['calls']])
