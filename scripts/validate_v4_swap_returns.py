"""Execute isolated V4 swaps with explicit synthetic fee exemption."""
import json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import word,mapping
from v4_delta import decode
HOOK='0x4adbfa936020fb330587ee1862478316da5ba0cc'
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'
ROUTER='0x204faca1764b154221e35c0d20abb3c525710498'
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
cases=json.loads(Path('tests/fixtures/universal_v4_intent.json').read_text())
txs={r['tx']['tx']:r['tx'] for r in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines())}
for c in cases:seed['accounts'][HOOK]['storage'][mapping(int(txs[c['tx']]['from'],16),0)]='0x1'
p=dict(accounts=seed['accounts'],trace_execution=True,execute_targets=[ROUTER,MANAGER,HOOK])
def dynamic(b):return word(len(b))+b+bytes((-len(b))%32)
records=[]
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(p))
 for c in cases:
  tx=txs[c['tx']];payload=bytes.fromhex(c['payload'])
  raw=word(96)+word(160)+word(tx['timestamp']+3600)+dynamic(b'\x10')+word(1)+word(32)+dynamic(payload)
  result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(dict(tx,data='0x3593564c'+raw.hex())),text=True))
  assert result['error'] is None,result['error']
  returns=[r for r in result['execution_returns'] if r['to']==MANAGER and r['selector']=='0xf3cd914c']
  assert len(returns)==1 and returns[0]['result']=='Return'
  a,b=decode(returns[0]['output']);op=c['expected'];spent=a if op['zero'] else b;received=b if op['zero'] else a
  assert spent==op['amount'] and received>0
  hooks=[r for r in result['execution_returns'] if r['to']==HOOK and r['selector'] in ('0x575e24b4','0xb47b2fb1')]
  assert len(hooks)==2 and all(r['result']=='Return' and not int(r['output'][66:],16) for r in hooks)
  records.append(dict(tx=c['tx'],amount0=str(a),amount1=str(b),output_amount=str(received),manager_return=returns[0],root_success=result['execution_success']))
Path('reports/amm/v4-swap-return-validation.json').write_text(json.dumps(dict(records=records,
 caveat='Archived state with synthetic flag=true; isolated V4 action, settlement stopped. Not historical parity or continuous state.'),indent=2)+'\n')
print(f'{len(records)} local manager return deltas, both directions; hook deltas zero with synthetic flag=true')
