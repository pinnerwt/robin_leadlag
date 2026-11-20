"""Execute index4 swap prefix on archived state; missing dependencies fail closed."""
import argparse,json,subprocess,tempfile
from pathlib import Path
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');a=ap.parse_args()
seed=json.load(open(a.seed));source=json.load(open('reports/amm/routera3d-index4-anchor-probe.json'))
seed.setdefault('execute_targets',[]).extend(['0x7615926023bb149f36095645c2a81dc367d39750','0xc0ed888afe87ed1acf01d9f19bb850159e3ce434','0xc63d7338c178e805c544b8f897066bd3bbcbe136'])
seed.setdefault('delegate_targets',[]).extend(['0x1642634c8cb1c9f1b84c9a1a08534f8c3f4e89f8','0x1ad7a8703ebff81c0d753190938f228672ec7e42'])
cases=[c for c in source['cases'] if c['tail']]
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(seed))
 rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(c['transaction'])+'\n' for c in cases),text=True).splitlines()))
result=dict(caveat='Synthetic anchor envelopes and mixed-era research code. No missing storage substitution or log replay.',cases=[dict(tail=c['tail'],transaction=c['transaction'],result=r) for c,r in zip(cases,rows)])
Path('reports/amm/routera3d-index4-execution-probe.json').write_text(json.dumps(result,indent=2)+'\n')
for c in result['cases']:
 r=c['result'];print(c['tail'],r['error'],[(x['to'],x['data'][:10]) for x in r['calls']])
