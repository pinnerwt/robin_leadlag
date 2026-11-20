"""Reproduce sender-flag branches; synthetic flags are never live checkpoint data."""
import json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import mapping
from v3_calldata import word
ROUTER='0x204faca1764b154221e35c0d20abb3c525710498'
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'
HOOK='0x4adbfa936020fb330587ee1862478316da5ba0cc'
source=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
tx=next(r['tx'] for r in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()) if r['tx']['tx'].startswith('0x4c947d'))
slot=mapping(int(tx['from'],16),0);cases=[]
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 for flag in (0,1):
  accounts=json.loads(json.dumps(source['accounts']))
  accounts[HOOK]['storage'][slot]=hex(flag)
  seed=dict(accounts=accounts,trace_execution=True,trace_hashes=True,execute_targets=[ROUTER,MANAGER,HOOK])
  Path(tmp.name).write_text(json.dumps(seed))
  result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx),text=True))
  mints=[c for c in result['execution_calls'] if c['to']==MANAGER and c['data'].startswith('0x156e29f6')]
  assert len(mints)==(1 if flag==0 else 0)
  mint_amount=word(bytes.fromhex(mints[0]['data'][10:]),2) if mints else 0
  cases.append(dict(flag=flag,claim_mint_amount=str(mint_amount),result=result))
input_amount=214861077224598053847040
assert int(cases[0]['claim_mint_amount'])==input_amount*3//100
Path('reports/amm/v4-hook-flag-validation.json').write_text(json.dumps(dict(sender=tx['from'],slot=slot,
 input_amount=str(input_amount),cases=cases,caveat='Single observed amount: branch evidence, not generalized fee formula or real flag value'),indent=2)+'\n')
print('Flag0: claim mint equals 3% of input; flag1: no claim mint. Actual initial flag remains unknown.')
