"""Offline caller/origin fee-helper configuration interventions."""
import copy,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import mapping,word
HELPER='0xaa48aaef655fb7cd7acc04717f66022a4771a345';POOL='0x7615926023bb149f36095645c2a81dc367d39750';CALLER='0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880';ORIGIN='0x1111111111111111111111111111111111111111'
seed=json.load(open('reports/amm/routera3d-index4-blocks-dependencies.json'));h=seed['anchor'];seed.update(trace_execution=True,trace_hashes=True)
profiles=[(0,False,0),(100,False,999),(100,True,0),(100,True,250000),(0,True,250000),(1000000,False,0)]
cases=[]
for same in (False,True):
 for caller_profile in profiles:
  for origin_profile in ([(500,False,0),(500,True,750000)] if not same else [caller_profile]):
   s=copy.deepcopy(seed);storage=s['accounts'][HELPER]['storage']
   for address,profile in [(CALLER,caller_profile)]+([] if same else [(ORIGIN,origin_profile)]):
    global_rate,enabled,pool_rate=profile;base=int(mapping(int(address,16),2),16)
    storage[hex(base)]=hex((global_rate<<8)|int(enabled));storage[mapping(int(POOL,16),base+1)]=hex(pool_rate)
   tx=dict(tx='caller-adjustment',to=HELPER,data='0xcd713a43'+word(int(POOL,16)).hex()+word(int(CALLER,16)).hex(),sequence=int(h['number'],16),timestamp=int(h['timestamp'],16),**{'from':CALLER if same else ORIGIN})
   with tempfile.NamedTemporaryFile(suffix='.json') as f:
    Path(f.name).write_text(json.dumps(s));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix',f.name],input=json.dumps(tx)+'\n',text=True))
   assert r['execution_success'] and not r['error'] and not r['calls'],r['error']
   value=int(r['output'],16);cases.append(dict(same_origin=same,caller_profile=caller_profile,origin_profile=origin_profile,value=value,result=r))
report=dict(anchor_hash=h['hash'],cases=cases,caveat='Explicit synthetic configuration words, real helper bytecode. Values are not current account settings; application to pool fee studied separately.')
Path('reports/amm/routera3d-index4-caller-adjustment-probe.json').write_text(json.dumps(report,indent=2)+'\n')
for c in cases:print(c['same_origin'],c['caller_profile'],c['origin_profile'],c['value'])
