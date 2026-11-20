"""Join V3 and Metric local state at one archived anchor; not historical replay."""
import json
import subprocess
from pathlib import Path
from cc1a_route import plan,bind_output
from v3_state import State

v3=json.loads(Path('captures/startup-v9-quotes.json').read_text())
metric=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
assert v3['anchor']['hash']==metric['anchor']['hash'],'incoherent checkpoint'
rows=[];requests=[]
for line in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines():
    tx=json.loads(line)['tx']
    if (tx['to'] or '').lower()!='0xcc1ae96cd8479f896a8dba85eab09a694b929b6c':continue
    try:ops=plan(tx['data'])
    except ValueError:continue
    p=next(p for p in v3['pools'] if p['pool']==ops[0]['pool'])
    state=State.load(p)
    result=state.swap(ops[0]['zero'],ops[0]['amount'],ops[0]['limit'],True)
    amount=bind_output(ops[1],[result])
    request=dict(header=metric['parent_header'],pool=ops[1]['pool'],zero=ops[1]['zero'],
                 amount=str(amount),sender=ops[1]['sender'],recipient=ops[1]['recipient'],commit=False)
    rows.append(dict(tx=tx['tx'],plan=ops,v3_result=result,metric_request=request));requests.append(request)
assert requests,'no supported samples'
output=subprocess.check_output(['target/release/examples/metric_transition','captures/startup-v9-dependencies.json'],
                               input=''.join(json.dumps(r)+'\n' for r in requests),text=True)
responses=[json.loads(line) for line in output.splitlines()]
assert len(responses)==len(rows)
for row,response in zip(rows,responses):row['metric_response']=response
report=dict(cross_venue_state_coherent=False, limitation='Metric DB does not receive first-leg V3 storage changes; results are dependency probes only', anchor_hash=v3['anchor']['hash'],purpose='Independent route simulations at shared archived anchor, not historical swap replay or live reducer',cases=rows)
Path('reports/amm/routercc1-route-probe.json').write_text(json.dumps(report,indent=2)+'\n')
for r in rows:print(r['tx'][:12],r['metric_request']['amount'],r['metric_response'].get('error','individual simulations returned; cross-venue state NOT synchronized'))
