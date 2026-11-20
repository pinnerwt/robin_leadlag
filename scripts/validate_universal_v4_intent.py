"""Isolate V4 actions and compare their pool-manager call to local bytecode."""
import json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import word as encode
from v3_calldata import word,blob,array,signed
from universal_v4_intent import inspect,MANAGER
ROUTER='0x204faca1764b154221e35c0d20abb3c525710498'
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
p=dict(accounts=seed['accounts'],trace_execution=True,execute_targets=[ROUTER,MANAGER])
def dynamic(b):return encode(len(b))+b+bytes((-len(b))%32)
cases=[]
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(p))
 for row in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()):
  tx=row['tx']
  if (tx['to'] or '').lower()!=ROUTER:continue
  d=bytes.fromhex(tx['data'][10:])
  for command,payload in zip(blob(d,word(d,0)),array(d,word(d,1))):
   if command!=16:continue
   try:op=inspect(payload)
   except ValueError:continue
   # Isolate only this command; preceding V3 state and funding aren't simulated.
   raw=encode(96)+encode(160)+encode(word(d,2))+dynamic(b'\x10')+encode(1)+encode(32)+dynamic(payload)
   isolated=dict(tx,data='0x3593564c'+raw.hex())
   result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(isolated),text=True))
   assert result['error'] is None,result['error']
   calls=[c for c in result['execution_calls'] if c['to']==MANAGER and c['data'].startswith('0xf3cd914c')]
   assert len(calls)==1
   b=bytes.fromhex(calls[0]['data'][10:])
   assert [word(b,i) for i in range(5)]==[int(op['currency0'],16),int(op['currency1'],16),op['fee'],op['tick_spacing'],int(op['hooks'],16)]
   assert bool(word(b,5))==op['zero'] and signed(word(b,6))==op['amount'] and word(b,7)==op['limit']
   cases.append(dict(tx=tx['tx'],payload=payload.hex(),expected=op))
assert len(cases)==9
Path('tests/fixtures/universal_v4_intent.json').write_text(json.dumps(cases,indent=2)+'\n')
Path('reports/amm/universal-v4-intent-validation.json').write_text(json.dumps(dict(pool_manager_matches=len(cases),
 hook='0x4adbfa936020fb330587ee1862478316da5ba0cc',missing_hook_slot='0x1f3d4eafd51a69cb60de482c73a03ffc13f9c95847b73e031925db7e1cc5c5e3',
 caveat='Isolated action prefix only; custom hook output and subsequent balance-based V3 input unresolved'),indent=2)+'\n')
print('9 isolated V4 manager intents match bytecode; hook pricing unresolved')
