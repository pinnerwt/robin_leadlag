"""Initialize known router balances from an existing local EVM checkpoint.

No RPC. Missing storage remains unknown; proxy targets come from seeded slots.
"""
import json,subprocess,tempfile
from pathlib import Path
IMPLEMENTATION='0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
TOKENS=['0x0bd7d308f8e1639fab988df18a8011f41eacad73','0x5fc5360d0400a0fd4f2af552add042d716f1d168']
ROUTERS=['0x204faca1764b154221e35c0d20abb3c525710498','0xc9a1dcff54632b408f2b0e048d8b7d3261697144']
def inventory_at(report,router,anchor_hash,tokens):
 if report['anchor_hash']!=anchor_hash:raise ValueError('inventory checkpoint anchor differs')
 entries={e['token']:e for e in report['entries'] if e['router']==router.lower()}
 balances={}
 for token in tokens:
  entry=entries.get(token)
  if entry is None or 'balance' not in entry:raise ValueError('missing local inventory: '+token)
  value=int(entry['balance'])
  if not 0<=value<1<<256:raise ValueError('invalid local inventory')
  balances[token]=value
 return balances

def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 reference=json.loads(Path('tests/fixtures/universal_roundtrip.json').read_text())[0]['tx']
 targets=[]
 for token in TOKENS:
  implementation=int(seed['accounts'][token]['storage'][IMPLEMENTATION],16)
  if implementation>>160:raise ValueError('implementation padding')
  targets.append('0x'+implementation.to_bytes(20,'big').hex())
 p=dict(accounts=seed['accounts'],delegate_targets=targets,trace_execution=True,trace_hashes=True)
 identities=[(router,token) for router in ROUTERS for token in TOKENS]
 requests=[dict(reference,to=token,data='0x70a08231'+int(router,16).to_bytes(32,'big').hex(),value='0x0') for router,token in identities]
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  Path(tmp.name).write_text(json.dumps(p))
  output=subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True)
 rows=list(map(json.loads,output.splitlines()));assert len(rows)==len(identities)
 entries=[]
 for (router,token),result in zip(identities,rows):
  entry=dict(router=router,token=token,result=result)
  if result['error'] is None and result['execution_success'] and not result['calls'] and len(result.get('output') or '')==66:
   entry['balance']=str(int(result['output'],16))
  else:entry['unknown']=result['error'] or 'incomplete balanceOf execution'
  entries.append(entry)
 report=dict(anchor_hash=seed['anchor']['hash'],anchor_number=seed['anchor']['number'],entries=entries,
             caveat='Balances at archived checkpoint only, not at later transaction time')
 Path('reports/amm/router-inventory-checkpoint.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps([{k:v for k,v in e.items() if k!='result'} for e in entries]))
if __name__=='__main__':main()
