"""Research prefix with synthetic cached balances and balance-delta funding.
Run after constructing the research seed; not live checkpoint data.
"""
import json,subprocess,sys,copy
sys.path.insert(0,'scripts');from router777_plan import plan;from v3_calldata import word,address
source=json.load(open('captures/startup-v9-dependencies.json'))
R='0x7777857616fb37f0cfa262e9bb945e828312df17';H='0x1111113ccf1426a8e30e2bff5e005d929bf6a90a'
base=dict(accounts=source['accounts'],trace_execution=True,execute_targets=[R,H,'0x111111338c5091e8440b67b168bae16a668ac0de'],getters={})
from bootstrap_state import mapping
U='0x5fc5360d0400a0fd4f2af552add042d716f1d168';W='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
base['accounts'][R]['storage'][mapping(int(U,16),11)]=base['accounts'][R]['storage']['0x9']
base['accounts'][R]['storage'][mapping(int(U,16),10)]='0x0'
for token,balance in [(W,10**18),(U,10**9)]:
 base['getters'][token]={'0x70a08231'+int(R,16).to_bytes(32,'big').hex():'0x'+balance.to_bytes(32,'big').hex()}
traces=json.load(open('reports/amm/router777-callback-prefix.json'))
by_hash={r['tx']['tx']:r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl'))}
txs=[by_hash[r['tx']] for r in traces];rows=[]
for trace in traces:
 for c in trace['execution_calls']:
  if (c['to'] in (W,U) and c['data'].startswith('0x23b872dd')) or (c['to']=='0x26ffc7d378e8e49be2c483295a3e3e511f96a468' and c['data'].startswith('0x70a08231')):
   base['getters'].setdefault(c['to'],{})[c['data']]='0x'+(1).to_bytes(32,'big').hex()

for tx,tr in zip(txs,traces):
 p=copy.deepcopy(base);route=plan(tx['data']);token=route['token_out'];calls=[c for c in tr['execution_calls'] if c['data'].startswith('0xb00bbd10')];amount=next(word(bytes.fromhex(c['data'][10:]),3) for c in calls if address(word(bytes.fromhex(c['data'][10:]),2))==token)
 k='0x70a08231'+int('7777857616fb37f0cfa262e9bb945e828312df17',16).to_bytes(32,'big').hex();before=int(p['getters'][token][k],16);p['getters'][token][k]=['0x'+n.to_bytes(32,'big').hex() for n in [before,before+amount,before+amount,before+amount]]
 open('/tmp/router777-sequence-seed.json','w').write(json.dumps(p));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix','/tmp/router777-sequence-seed.json'],input=json.dumps(tx),text=True));print(r['error'],r['output'],[(c['to'],c['data'][:10]) for c in r['calls']]);rows.append(r)
open('reports/amm/router777-sequence-prefix.json','w').write(json.dumps(rows,indent=2))
