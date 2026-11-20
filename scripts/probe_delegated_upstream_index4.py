"""Inspect saved proxy pool getters and first actual swap prefix; no RPC."""
import json,subprocess,tempfile
from pathlib import Path
IMPL='0x1642634c8cb1c9f1b84c9a1a08534f8c3f4e89f8'
def main():
 s=json.loads(Path('captures/startup-v9-dependencies.json').read_text());s.update(trace_execution=True,delegate_targets=[IMPL])
 cases=json.loads(Path('reports/amm/delegated-single-callback-probe.json').read_text())['cases']
 c=next(c for c in cases if c['tx']['tx'].startswith('0x9bc1e70a'))
 requests=[]
 for action in c['plan']['actions'][:2]:
  for name,sig in [('token0','0x0dfe1681'),('token1','0xd21220a7'),('slot0','0x3850c7bd'),('liquidity','0x1a686502'),('spacing','0xd0c93a7c')]:
   requests.append(dict(c['tx'],tx=action['target']+':'+name,to=action['target'],data=sig))
 call=c['result']['calls'][0]
 requests.append(dict(c['tx'],to=call['to'],data=call['data'],**{'from':c['tx']['to']}))
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  Path(tmp.name).write_text(json.dumps(s))
  results=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in requests),text=True).splitlines()))
 for tx,r in zip(requests,results):print(tx['tx'],r['error'],r.get('output'),[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 stages=[];tx=requests[-1];r=results[-1];s['execute_calls']=[]
 known={'0xc63d7338c178e805c544b8f897066bd3bbcbe136','0xc0ed888afe87ed1acf01d9f19bb850159e3ce434','0xaa48aaef655fb7cd7acc04717f66022a4771a345',tx['to']}
 s['delegate_targets'].append('0x1ad7a8703ebff81c0d753190938f228672ec7e42')
 for _ in range(12):
  if r['error'] or len(r['calls'])!=1:break
  call=r['calls'][0];key=call['to']+':'+call['data']
  if call['to'] not in known or key in s['execute_calls']:break
  s['execute_calls'].append(key)
  with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
   Path(tmp.name).write_text(json.dumps(s));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
  stages.append(r);print('next',r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/delegated-upstream-index4-probe.json').write_text(json.dumps(dict(stages=stages,execute_calls=s['execute_calls'],anchor=s['anchor']['hash'],requests=requests,results=results,caveat='Saved checkpoint getter/swap prefixes. No historical prestate or completed swap claim.'),indent=2)+'\n')
if __name__=='__main__':main()
