"""Execute actual router callback with explicit synthetic first-pool deltas."""
import copy,json
from pathlib import Path
from probe_delegated_kind8 import run
from probe_settler_tail_callback import pool_code
from router0480_first_swap import ROUTER

def main():
 prior=json.loads(Path('reports/amm/router0480-inventory.json').read_text());old=json.loads(Path('reports/amm/router0480-local-getters.json').read_text());base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());call=prior['cases'][0]['result']['calls'][0];d=bytes.fromhex(call['data'][10:]);offset=int.from_bytes(d[128:160],'big');n=int.from_bytes(d[offset:offset+32],'big');opaque=d[offset+32:offset+32+n];amount=int.from_bytes(d[64:96],'big',signed=True);word=lambda x:(x%(1<<256)).to_bytes(32,'big');rows=[]
 keep={ROUTER,prior['tx']['from'].lower(),'0x'+'00'*20,'0x1f7d7550b1b028f7571e69a784071f0205fd2efa'}
 base['accounts']={a:v for a,v in base['accounts'].items() if a in keep or a[2:] in prior['tx']['data'].lower()}
 for output in (1000000,2000000):
  seed=copy.deepcopy(base);reply=word(amount)+word(-output);cb=bytes.fromhex('fa461e33')+reply+word(96)+word(n)+opaque+bytes((-n)%32)
  seed['accounts'][call['to']]['code']='0x'+pool_code(cb,ROUTER,reply).hex();seed.update(trace_execution=True,execute_targets=[ROUTER],execute_calls=old['execute_calls']+[call['to']+':'+call['data']],getters={prior['synthetic_inventory_call']['to']:{prior['synthetic_inventory_call']['data']:'0x'+word(0).hex()}})
  # Keep real slot0 getter behavior: pool replacement also replaces getters, so replay saved getter outputs explicitly.
  for key in old['execute_calls']:
   if key.startswith(call['to']+':'):
    seed['execute_calls'].remove(key)
    account=base['accounts'][call['to']];slot=int(account['storage']['0x0'],16);tick=(slot>>160)&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
    values=[slot&((1<<160)-1),tick,(slot>>184)&65535,(slot>>200)&65535,(slot>>216)&65535,(slot>>232)&255,(slot>>240)&255]
    seed['getters'].setdefault(call['to'],{})['0x3850c7bd']='0x'+b''.join(word(v) for v in values).hex()
  r=run(seed,prior['tx']);stages=[r];getter_replays=[]
  for _ in range(4):
   if r['error'] or len(r['calls'])!=1:break
   pending=r['calls'][0]
   if pending['scheme']=='StaticCall' and pending['to']=='0x1f7d7550b1b028f7571e69a784071f0205fd2efa' and pending['data'].startswith('0x1698ee82'):
    seed['execute_calls'].append(pending['to']+':'+pending['data']);r=run(seed,prior['tx']);stages.append(r);continue
   if pending['scheme']!='StaticCall' or pending['to']!=call['to'] or pending['data'] not in ('0xc45a0155','0x0dfe1681','0xd21220a7','0xddca3f43','0xd0c93a7c'):break
   getter=run(base,dict(prior['tx'],to=pending['to'],data=pending['data'],**{'from':ROUTER}))
   if not getter['execution_success'] or getter['error']:break
   seed['getters'].setdefault(pending['to'],{})[pending['data']]=getter['output'];getter_replays.append(dict(call=pending,result=getter));r=run(seed,prior['tx']);stages.append(r)
  rows.append(dict(synthetic_output=output,callback='0x'+cb.hex(),getter_replays=getter_replays,stages=stages,result=r));print(output,r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/router0480-callback.json').write_text(json.dumps(dict(tx=prior['tx'],cases=rows,caveat='Mutated guard, synthetic first pool/token inventory and deltas; synthetic pool ignores callback success. Actual router callback only, no full transaction success claim.'),indent=2)+'\n')
if __name__=='__main__':main()
