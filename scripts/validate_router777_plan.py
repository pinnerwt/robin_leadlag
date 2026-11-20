"""Compare complete reconstructed primary bytes with independent prefix traces."""
import json
from pathlib import Path
from router777_plan import plan
traces=json.loads(Path('reports/amm/router777-cache-validation.json').read_text())['variants'][0]
txs={r['tx']['tx']:r['tx'] for r in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines())}
cases=[]
for trace in traces:
 tx=txs[trace['tx']];p=plan(tx['data'])
 assert p['primary']==trace['calls'][0]['data']
 cases.append(dict(calldata=tx['data'],expected=p))
assert len(cases)==8
Path('tests/fixtures/router777_plan.json').write_text(json.dumps(cases,indent=2)+'\n')
print('8 complete Aqua calldata rebuilds match bytecode, including nested callback payload')
