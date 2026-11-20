"""Explicit fee-cache interventions to map remaining upstream dependencies."""
import argparse,copy,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import mapping

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--discount',type=int);ap.add_argument('--no-rewards',action='store_true');ap.add_argument('--skip-post-hook',action='store_true');ap.add_argument('--leg',type=int,choices=(1,2),default=1);ap.add_argument('--synthetic-observation',action='store_true');args=ap.parse_args()
 if args.discount is not None and not 0<=args.discount<=1000000:raise ValueError('discount bounds')
 source=json.loads(Path('reports/amm/delegated-upstream-index4-probe.json').read_text())
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());tx=source['requests'][-1]
 if args.leg==2:
  chain=json.loads(Path('reports/amm/delegated-v3-chain-probe.json').read_text());call=chain['stages'][0]['calls'][0]
  tx=dict(tx,to=call['to'],data=call['data'])
 fee='0xc0ed888afe87ed1acf01d9f19bb850159e3ce434'
 key=mapping(int(tx['sequence']),int(mapping(int(tx['to'],16),4),16))
 seed.update(trace_execution=True,delegate_targets=['0x1642634c8cb1c9f1b84c9a1a08534f8c3f4e89f8','0x1ad7a8703ebff81c0d753190938f228672ec7e42'],execute_calls=source['execute_calls'])
 cases=[]
 for value in (17,242 if args.leg==1 else 511,1000):
  s=copy.deepcopy(seed);s['accounts'][fee]['storage'][key]=hex(value);observations={}
  if args.synthetic_observation:
   storage=s['accounts'][tx['to']]['storage'];packed=int(storage['0x6'],16);index=packed>>184&65535;card=packed>>200&65535
   for slot,word in [(17+index,int(tx['timestamp'])|(1<<248)),(17+(index+1)%card,0)]:
    if hex(slot) not in storage:storage[hex(slot)]=hex(word);observations[hex(slot)]=hex(word)

  if args.discount is not None:s['accounts']['0xaa48aaef655fb7cd7acc04717f66022a4771a345']['storage'][mapping(int(tx['from'],16),2)]=hex(args.discount<<8)
  if args.discount is not None:s['execute_targets']=['0xc63d7338c178e805c544b8f897066bd3bbcbe136','0xc0ed888afe87ed1acf01d9f19bb850159e3ce434','0xaa48aaef655fb7cd7acc04717f66022a4771a345','0xdd1705e23762f4d6e44d8c31bd8ea80c54612239','0x382409fad8503fbcdbb27a4211551fa03e884078','0x27d5eb73e7406675f6b0cbd037490ec3dba935a4','0xcc421483cd131a8fd6b68c37e46f244dbec4f797','0xf437f62053acb121665b8fdbfea8f214fb8e589d',tx['to']]
  if args.no_rewards:
   rewards='0xdd1705e23762f4d6e44d8c31bd8ea80c54612239'
   s['execute_targets'].remove(rewards)
   s['getters']={rewards:{'0x890054f8'+'00'*12+tx['to'][2:]: '0x'+'00'*32}}
  with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
   Path(tmp.name).write_text(json.dumps(s));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
  stages=[r]
  known={'0xc63d7338c178e805c544b8f897066bd3bbcbe136','0xaa48aaef655fb7cd7acc04717f66022a4771a345','0xdd1705e23762f4d6e44d8c31bd8ea80c54612239',tx['to']}
  for _ in range(12):
   if r['error'] or len(r['calls'])!=1:break
   c=r['calls'][0];entry=c['to']+':'+c['data']
   if c['to'] not in known or entry in s['execute_calls'] or c['data'] in s.get('getters',{}).get(c['to'],{}):break
   s['execute_calls'].append(entry)
   with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
    Path(tmp.name).write_text(json.dumps(s));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
   stages.append(r)
  if args.skip_post_hook:
   target='0x27d5eb73e7406675f6b0cbd037490ec3dba935a4'
   calls=[c for c in r['execution_calls'] if c['to']==target and c['data'].startswith('0x11f14a52')]
   if len(calls)!=1:raise ValueError('expected one post-hook call')
   s['execute_targets'].remove(target);s.setdefault('getters',{}).setdefault(target,{})[calls[0]['data']]='0x'
   with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
    Path(tmp.name).write_text(json.dumps(s));r=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
   stages.append(r)
  cases.append(dict(synthetic_observations=observations,synthetic_fee_cache=value,stages=stages,result=r));print(value,r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/delegated-upstream-cache-'+('leg2-' if args.leg==2 else '')+('probe' if args.discount is None else 'discount-'+str(args.discount))+('-no-rewards' if args.no_rewards else '')+('-skip-post-hook' if args.skip_post_hook else '')+('-synthetic-observation' if args.synthetic_observation else '')+'.json').write_text(json.dumps(dict(leg=args.leg,synthetic_post_hook_noop=args.skip_post_hook,synthetic_no_rewards=args.no_rewards,synthetic_discount=args.discount,tx=tx,slot=key,cases=cases,caveat='Synthetic known cache values, not historical fee evidence. All other state saved; missing dependencies remain errors.'),indent=2)+'\n')
if __name__=='__main__':main()
