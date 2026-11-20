"""Controlled mode40 framing interventions, no production decoder change."""
import argparse,json,subprocess,tempfile
from pathlib import Path
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
seed=json.load(open(a.seed));ref=json.loads(Path('tests/fixtures/routera3d_price.json').read_text())[0]
tx=next(r['tx'] for r in map(json.loads,open('reports/amm/optimistic-target-corpus.jsonl')) if r['tx']['tx']==ref['tx'])
header=bytes.fromhex(tx['data'][2:])[:13];requests=[];specs=[]
for mode,body,label in [(0xe1,'09f60001','e1_baseline'),(0x41,'09f60001','41_no_extra'),(0x41,'09f600010000','41_extra'),(0x42,'09f649f600050001','42_one_special'),(0x42,'49f649f600050001','42_two_special_short'),(0x42,'49f649f6000500010001','42_two_special_long')]:
    data=bytes([mode])+header[1:]+bytes.fromhex(body);requests.append(dict(tx,data='0x'+data.hex()));specs.append(label)
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
    Path(tmp.name).write_text(json.dumps(seed))
    rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True).splitlines()))
cases=[dict(label=l,transaction=t,result=r) for l,t,r in zip(specs,requests,rows)]
Path('reports/amm/routera3d-mode40-probe.json').write_text(json.dumps(dict(cases=cases,caveat='Synthetic envelopes and research seed; prefix framing only. No full transaction success implied.'),indent=2)+'\n')
print([(c['label'],c['result']['error'],c['result']['output'],[(x['to'],x['data'][:10]) for x in c['result']['calls']]) for c in cases])
