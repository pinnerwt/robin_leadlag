"""Synthetic funding/V3 output interventions to expose actual kind-8 call arguments."""
import argparse,json
from pathlib import Path
from probe_delegated_kind8 import run
from probe_delegated_funding import manager_code
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
USDG='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
V3='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=int,default=123456789);ap.add_argument('--active',action='store_true');args=ap.parse_args()
 prior=json.loads(Path('reports/amm/delegated-kind8-probe.json').read_text());tx=prior['tx'];root=tx['to'].lower()
 metadata=json.loads(Path('reports/amm/delegated-single-prefix-probe.json').read_text())['cases'][0]
 unlock=prior['prefix']['calls'][0];take=prior['callback']['calls'][0];manager=unlock['to']
 s=json.loads(Path('captures/startup-v9-dependencies.json').read_text());s['trace_execution']=True
 cb=bytes.fromhex('91dd7346'+unlock['data'][10:])
 s['accounts'][manager]=dict(code='0x'+manager_code(cb,root).hex(),balance=hex(10**30),nonce='0x0',storage={})
 lookup=metadata['result']['calls'][0]
 s['execute_calls']=[manager+':'+unlock['data'],manager+':'+take['data'],lookup['to']+':'+lookup['data']];s['execute_targets']=[root]
 s['getters']=metadata['synthetic_getters'];balance='0x70a08231'+'00'*12+root[2:]
 s['getters'].setdefault(WETH,{})['0xd0e30db0']='0x'
 s['getters'][WETH][balance]='0x'+'00'*32
 s['getters'].setdefault(USDG,{})[balance]=['0x'+'00'*32,'0x'+args.output.to_bytes(32,'big').hex()]
 s['getters'][USDG]['0x70a08231'+'00'*12+lookup['to'][2:]]=['0x'+'00'*32,'0x'+args.output.to_bytes(32,'big').hex()]
 stages=[]
 for _ in range(5):
  r=run(s,tx);stages.append(r);added=False
  print([(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
  for c in r['calls']:
   if c['to']==V3 and c['data'].startswith('0x128acb08'):
    d=bytes.fromhex(c['data'][10:]);amount=int.from_bytes(d[64:96],'big')
    s['getters'].setdefault(V3,{})[c['data']]='0x'+amount.to_bytes(32,'big').hex()+((-args.output)%(1<<256)).to_bytes(32,'big').hex();added=True
  if not added:break
 inner=None
 calls=[c for c in r['calls'] if c['to']==lookup['to'] and c['data'].startswith('0x9908fc8b')]
 if len(calls)==1:
  s['execute_calls'].append(calls[0]['to']+':'+calls[0]['data'])
  inner=run(s,tx)
  print('inner',inner['error'],[(c['to'],c['data'][:10]) for c in inner['calls']],flush=True)
 inner_pool=None
 if inner and len(inner['calls'])==1 and inner['calls'][0]['data']=='0x22f3e2d4':
  c=inner['calls'][0];s['execute_calls'].append(c['to']+':'+c['data'])
  inner_pool=run(s,tx)
  print('inner pool',inner_pool['error'],[(c['to'],c['data'][:10]) for c in inner_pool['calls']],flush=True)
 continuations=[];current=inner_pool
 for _ in range(6):
  if not current or current['error'] or len(current['calls'])!=1:break
  c=current['calls'][0]
  if c['scheme']!='StaticCall' or c['to'] not in s['accounts']:break
  key=c['to']+':'+c['data']
  if key in s['execute_calls']:break
  s['execute_calls'].append(key);current=run(s,tx);continuations.append(current)
  print('continuation',current['error'],[(c['to'],c['data'][:10]) for c in current['calls']],flush=True)
 active_probe=None;transfer_probe=None
 if args.active:
  target='0x135a93116097ec2a3a0892686fbd3f1b37753d78';key=target+':0x22f3e2d4'
  s['execute_calls'].remove(key);s['getters'].setdefault(target,{})['0x22f3e2d4']='0x'+(1).to_bytes(32,'big').hex()
  active_probe=run(s,tx)
  print('synthetic active',active_probe['error'],[(c['to'],c['data'][:10]) for c in active_probe['calls']],flush=True)
  calls=active_probe['calls']
  if len(calls)==1 and calls[0]['to']==USDG and calls[0]['data'].startswith('0xa9059cbb'):
   c=calls[0];s['getters'].setdefault(USDG,{})[c['data']]='0x'+(1).to_bytes(32,'big').hex()
   transfer_probe=run(s,tx)
   print('synthetic transfer',transfer_probe['error'],[(c['to'],c['data'][:10]) for c in transfer_probe['calls']],flush=True)
 report=dict(transfer_probe=transfer_probe,synthetic_active=args.active,active_probe=active_probe,continuations=continuations,inner_pool=inner_pool,inner=inner,tx=tx,synthetic_v3_output=args.output,synthetic_getters=s['getters'],stages=stages,result=r,
  caveat='Actual router, synthetic manager funding, deposit and V3 output/full credit; prefix only, not transaction success.')
 Path('reports/amm/delegated-kind8-funded-'+str(args.output)+('-active' if args.active else '')+'.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
