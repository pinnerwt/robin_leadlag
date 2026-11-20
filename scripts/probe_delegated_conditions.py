"""Original delegated condition bytecode with controlled getter prices."""
import json,copy,subprocess,tempfile,argparse
from pathlib import Path
from delegated_compressed import inspect
from probe_delegated_callback import callback_code
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--boundary-only',action='store_true');ap.add_argument('--checkpoint',action='store_true');args=ap.parse_args()
source=json.loads(Path('reports/amm/delegated-router-funded-balance-0.json').read_text())['tx']
plan=inspect(source['data']);root=source['to'].lower()
prefix=next(r for r in map(json.loads,Path('reports/amm/delegated-router-getter-prefix.jsonl').read_text().splitlines()) if r['tx']==source['tx'])
call=prefix['calls'][0];manager=call['to'];callback=bytes.fromhex('91dd7346'+call['data'][10:])
seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
seed.update(trace_execution=True,control_targets=[root],math_targets=[root],execute_targets=[root],execute_calls=[manager+':'+call['data']])
seed['accounts'][manager]=dict(code='0x'+callback_code(callback,root).hex(),balance='0x0',nonce='0x0',storage={})
quotes=json.loads(Path('captures/startup-v9-quotes.json').read_text())
seed['getters']={}
for p in quotes['pools']:
 for selector,token in zip(('0x0dfe1681','0xd21220a7'),p['tokens']):
  seed['getters'].setdefault(p['pool'],{})[selector]='0x'+int(token,16).to_bytes(32,'big').hex()
cases=[]
for shift,threshold in ([(0,None)] if args.checkpoint else [(-1,n) for n in (858991,858992,858993)] if args.boundary_only else [(n,None) for n in (-3,-2,-1,0,1,2,3)]):
 s=copy.deepcopy(seed);prices=[];tx=copy.deepcopy(source)
 if threshold is not None:
  old=bytes.fromhex(plan['condition_groups'][0]['prefix']);new=threshold.to_bytes(8,'big');marker=b'\x83'+old
  raw=bytearray.fromhex(tx['data'][2:]);offset=plan['conditions_offset']+1;raw[offset:offset+8]=new;tx['data']='0x'+raw.hex()
  unlock=bytes.fromhex(call['data'][2:]);assert unlock.count(marker)==1;unlock=unlock.replace(marker,b'\x83'+new)
  cb=bytes.fromhex('91dd7346')+unlock[4:];s['accounts'][manager]['code']='0x'+callback_code(cb,root).hex();s['execute_calls']=[manager+':0x'+unlock.hex()]
 for gi,g in enumerate(plan['condition_groups']):
  for ri,r in enumerate(g['records']):
   price=r['value']*(10000+shift)//10000 if gi==0 and ri==0 else r['value']
   if args.checkpoint:
    from delegated_local import read
    from v3_state import State
    local=json.loads(Path('reports/amm/delegated-local-input.json').read_text())['state']
    local['curves']={a:State.load(v) for a,v in local['curves'].items()}
    price=int.from_bytes(read(local,r),'big')
   s['getters'].setdefault(r['target'],{})[r['calldata']]='0x'+price.to_bytes(32,'big').hex();prices.append(price)
 with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
  Path(tmp.name).write_text(json.dumps(s))
  result=json.loads(subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=json.dumps(tx)+'\n',text=True))
 cases.append(dict(threshold_override=threshold,shift_bps=shift,prices=prices,result=result))
 print(shift,result['error'],[(c['to'],c['data'][:10]) for c in result['calls']],[(m['a'],m['b']) for m in result['math_ops'] if m['pc']==0x1d58],flush=True)
Path('reports/amm/delegated-condition-'+('checkpoint' if args.checkpoint else 'boundary' if args.boundary_only else 'score')+'-probe.json').write_text(json.dumps(dict(plan=plan,cases=cases,caveat='Synthetic getter values, original callback evaluation. No full router success claim.'),indent=2)+'\n')
