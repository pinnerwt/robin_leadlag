"""Single-route parser validation through actual-code prefix with synthetic metadata getters."""
import json,copy,subprocess,tempfile
from pathlib import Path
from delegated_single import inspect
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());cases=[]
for tx in map(json.loads,Path('reports/amm/delegated-router-txs.jsonl').read_text().splitlines()):
 if tx['data'][:12] not in ('0x0c89e77a00','0x0c89e77a80'):continue
 plan=inspect(tx['data']);s=copy.deepcopy(seed);s['trace_execution']=True;s['getters']={};synthetic=[]
 if plan['condition']:
  for r in plan['condition']['records']:s['getters'].setdefault(r['target'],{})[r['calldata']]='0x'+r['value'].to_bytes(32,'big').hex()
 for a in plan['actions']:
  if a['kind']==1:
   for selector,token in zip(('0x0dfe1681','0xd21220a7'),(a['currency0'],a['currency1'])):s['getters'].setdefault(a['target'],{})[selector]='0x'+int(token,16).to_bytes(32,'big').hex()
  for address in (a['target'],a['currency0'],a['currency1']):
   if address not in s['accounts']:
    synthetic.append(address);s['accounts'][address]=dict(code='0x00',balance='0x0',nonce='0x0',storage={})
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  Path(tmp.name).write_text(json.dumps(s));result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
 cases.append(dict(tx=tx,plan=plan,synthetic_accounts=synthetic,synthetic_getters=s['getters'],result=result))
 print(tx['tx'][:12],result['error'],[(c['to'],c['data'][:10]) for c in result['calls']],flush=True)
Path('reports/amm/delegated-single-prefix-probe.json').write_text(json.dumps(dict(cases=cases,caveat='Research parser, synthetic condition/metadata getters and marked account placeholders. Prefix only.'),indent=2)+'\n')
