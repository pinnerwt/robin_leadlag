"""Compare shared allocation reducer to both successful 777 settlement traces."""
import json
from pathlib import Path
from router777_plan import allocation_candidate,plan
from hub_state import primary_keys,HUB
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
storage={int(k,16):int(v,16) for k,v in seed['accounts'][HUB]['storage'].items()}
cases=json.loads(Path('tests/fixtures/router777_plan.json').read_text())
pools=json.loads(Path('tests/fixtures/universal_permit.json').read_text())['pools']
fixtures=[]
for index,file in [(0,'reports/amm/router777-tail-0.json'),(-1,'reports/amm/router777-tail-prefix.json')]:
 c=cases[index];r=plan(c['calldata']);keys=primary_keys(r['primary'])['token_slots']
 pi,po=[storage[int(keys[t],16)] for t in (r['token_in'],r['token_out'])]
 result=allocation_candidate(c['calldata'],pi,po,pools)
 trace=json.loads(Path(file).read_text());assert trace['execution_success']
 writes={int(w['slot'],16):int(w['value'],16) for w in trace['storage_writes'] if w['address']==HUB}
 assert result['allocation_in']==writes[int(keys[r['token_in']],16)]
 assert result['allocation_out']==writes[int(keys[r['token_out']],16)]
 fixtures.append(dict(calldata=c['calldata'],packed_in=str(pi),packed_out=str(po),allocation_in=str(result['allocation_in']),allocation_out=str(result['allocation_out'])))
Path('tests/fixtures/router777_allocations.json').write_text(json.dumps(dict(pools=pools,cases=fixtures),indent=2)+'\n')
print('Both 777 directions: shared reducer matches final successful synthetic hub writes')
