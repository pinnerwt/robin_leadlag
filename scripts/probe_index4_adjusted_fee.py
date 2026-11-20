"""Observe how helper adjustment applies to cold/warm fee cache, offline."""
import copy,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import mapping
POOL='0x7615926023bb149f36095645c2a81dc367d39750';FEE='0xc0ed888afe87ed1acf01d9f19bb850159e3ce434';HELPER='0xaa48aaef655fb7cd7acc04717f66022a4771a345';CALLER='0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880'
seed=json.load(open('reports/amm/routera3d-index4-ticks-dependencies.json'));source=json.load(open('reports/amm/routera3d-index4-crossing-probe.json'));reference=source['cases'][0];r=reference['stages'][-1]
seed.update(trace_execution=True,trace_hashes=True,math_targets=[FEE])
seed['execute_targets']=sorted({c['code'] for c in r['execution_calls'] if c['scheme'] in ('Call','StaticCall') and int(c['code'],16)>65535 and c['code'] not in ('0x0bd7d308f8e1639fab988df18a8011f41eacad73','0x5fc5360d0400a0fd4f2af552add042d716f1d168')})
seed['delegate_targets']=sorted({c['code'] for c in r['execution_calls'] if c['scheme']=='DelegateCall'})
profile=mapping(int(CALLER,16),2);cache=mapping(int(seed['anchor']['number'],16),int(mapping(int(POOL,16),4),16));cases=[]
for side in (0,1):
 reference=source['cases'][side]
 for stored in (0,263):
  for adjustment in (0,1,100000,250000,500000,999999,1000000):
   s=copy.deepcopy(seed);s['accounts'][HELPER]['storage'][profile]=hex(adjustment<<8);s['accounts'][FEE]['storage'][cache]=hex(stored)
   with tempfile.NamedTemporaryFile(suffix='.json') as f:
    Path(f.name).write_text(json.dumps(s));result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',f.name],input=json.dumps(reference['transaction'])+'\n',text=True))
   returns=[x for x in result['execution_returns'] if x['to']==FEE and x['selector']=='0xd3e6bf58'];assert len(returns)==1 and returns[0]['result']=='Return',(adjustment,result['error'])
   value=int(returns[0]['output'],16);cases.append(dict(side=side,stored=stored,adjustment=adjustment,fee=value,result=result))
Path('reports/amm/routera3d-index4-adjusted-fee-probe.json').write_text(json.dumps(dict(anchor_hash=seed['anchor']['hash'],cases=cases,caveat='Synthetic caller profile, actual fee callback; pool stopped at token transfer.'),indent=2)+'\n')
for c in cases:print(c['stored'],c['adjustment'],c['fee'])
