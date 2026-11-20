"""Bounded nested callback discovery with explicit synthetic swap deltas."""
import argparse,copy,json
from pathlib import Path
from probe_delegated_kind8 import run
from probe_settler_tail_callback import pool_code
from router0480_first_swap import ROUTER
F='0x1f7d7550b1b028f7571e69a784071f0205fd2efa'
def word(n):return (n%(1<<256)).to_bytes(32,'big')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--a2',action='store_true');ap.add_argument('--assume-registration',action='store_true');ap.add_argument('--pay-transfers',action='store_true');ap.add_argument('--minimum',type=int);ap.add_argument('--final-inventory',type=int,default=100);args=ap.parse_args();synthetic_registrations=[];synthetic_transfers=[];last_factory=None
 prior=json.loads(Path('reports/amm/router0480-inventory.json').read_text());old=json.loads(Path('reports/amm/router0480-local-getters.json').read_text());base=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 if args.a2:
  from router0480_guards import inspect
  a2=json.loads(Path('reports/amm/router0480-a2.json').read_text());prior=dict(prior,tx=a2['tx']);raw=bytearray.fromhex(prior['tx']['data'][2:]);old=dict(old,execute_calls=[])
  for g in inspect(prior['tx']['data'])['guards']:
   answer=run(base,dict(prior['tx'],to=g['pool'],data=g['getter']))
   if not answer['execution_success'] or answer['error']:raise ValueError('missing actual guard getter')
   price=int(answer['output'][2:66],16);raw[g['limit_offset']:g['limit_offset']+20]=price.to_bytes(20,'big');old['execute_calls'].append(g['pool']+':'+g['getter'])
  prior['tx']=dict(prior['tx'],data='0x'+raw.hex())
 tx=prior['tx'];keep={ROUTER,tx['from'].lower(),'0x'+'00'*20,F,'0x16494a80e08bcb9285d87b67149d7b01774d82f8','0x8c3bbdabf7b610d54097420e485a5e0e7bd68684'};base['accounts']={a:v for a,v in base['accounts'].items() if a in keep or a[2:] in tx['data'].lower()};s=copy.deepcopy(base)
 if args.minimum is not None:
  if args.minimum<0 or args.final_inventory<0:raise ValueError('negative intervention')
  raw=bytearray.fromhex(tx['data'][2:]);tail=int.from_bytes(raw[2+2*(raw[0]-1):4+2*(raw[0]-1)],'big');offset=int.from_bytes(raw[tail+3:tail+5],'big');raw[offset:offset+16]=args.minimum.to_bytes(16,'big');tx=dict(tx,data='0x'+raw.hex())
 balance=prior['synthetic_inventory_call'];s.update(delegate_targets=['0x8c3bbdabf7b610d54097420e485a5e0e7bd68684'] if args.a2 else [],trace_execution=True,execute_targets=[ROUTER],execute_calls=old['execute_calls'].copy(),getters={balance['to']:{balance['data']:'0x'+word(0).hex()}});stages=[];swaps=[];getters=[]
 if args.minimum is not None:s['getters'][balance['to']][balance['data']]=['0x'+word(100).hex(),'0x'+word(args.final_inventory).hex()]
 for _ in range(24):
  r=run(s,tx);stages.append(r)
  if args.assume_registration and r['error'] and 'unknown slot '+F.lower() in r['error'].lower() and last_factory is not None:
   key=last_factory['to']+':'+last_factory['data'];s['execute_calls'].remove(key);value='0x'+word(int(swaps[-1]['call']['to'],16)).hex();s['getters'].setdefault(F,{})[last_factory['data']]=value;synthetic_registrations.append(dict(call=last_factory,value=value));last_factory=None;continue
  if r['error'] or len(r['calls'])!=1:break
  c=r['calls'][0];sel=c['data'][:10];key=c['to']+':'+c['data']
  if sel=='0x128acb08' and len(swaps)<3:
   if any(x['call']['to']==c['to'] for x in swaps):raise ValueError('repeated synthetic pool')
   d=bytes.fromhex(c['data'][10:]);zero=bool(int.from_bytes(d[32:64],'big'));amount=int.from_bytes(d[64:96],'big',signed=True)
   if amount<=0:raise ValueError('only exact input probe')
   off=int.from_bytes(d[128:160],'big');n=int.from_bytes(d[off:off+32],'big');opaque=d[off+32:off+32+n];output=1000000;delta=[amount,-output] if zero else [-output,amount];reply=b''.join(word(x) for x in delta);cb=bytes.fromhex('2c8958f6' if args.a2 and len(swaps)>0 else 'fa461e33')+reply+word(96)+word(n)+opaque+bytes((-n)%32)
   # Preserve original getters before replacing just this pool's swap execution.
   existing=[k for k in s['execute_calls'] if k.startswith(c['to']+':')]
   for k in existing:
    data=k.split(':',1)[1];g=run(base,dict(tx,to=c['to'],data=data,**{'from':ROUTER}))
    if not g['execution_success'] or g['error']:raise ValueError('saved getter unavailable')
    s['getters'].setdefault(c['to'],{})[data]=g['output'];s['execute_calls'].remove(k);getters.append(dict(call=dict(to=c['to'],data=data),result=g))
   s['accounts'][c['to']]['code']='0x'+pool_code(cb,ROUTER,reply).hex();s['execute_calls'].append(key);swaps.append(dict(call=c,synthetic_deltas=delta,callback='0x'+cb.hex()));continue
  if args.pay_transfers and sel=='0xa9059cbb':
   if c['data'] in s['getters'].get(c['to'],{}):break
   s['getters'].setdefault(c['to'],{})[c['data']]='0x'+word(1).hex();synthetic_transfers.append(c);continue
  if c['scheme']=='StaticCall' and ((c['to']==F and sel=='0x1698ee82') or (c['to']=='0x16494a80e08bcb9285d87b67149d7b01774d82f8' and sel=='0xd8ed2241')):
   if key in s['execute_calls']:break
   s['execute_calls'].append(key);last_factory=c;continue
  if c['scheme']=='StaticCall' and any(x['call']['to']==c['to'] for x in swaps) and sel in ('0xc45a0155','0x0dfe1681','0xd21220a7','0xddca3f43','0xd0c93a7c'):
   g=run(base,dict(tx,to=c['to'],data=c['data'],**{'from':ROUTER}))
   if not g['execution_success'] or g['error']:break
   s['getters'].setdefault(c['to'],{})[c['data']]=g['output'];getters.append(dict(call=c,result=g));continue
  break
 report=dict(tx=tx,inventory_intervention=None if args.minimum is None else dict(start=100,end=args.final_inventory,minimum=args.minimum),synthetic_registrations=synthetic_registrations,synthetic_transfers=synthetic_transfers,swaps=swaps,getter_replays=getters,stages=stages,result=r,caveat='Mutated guard and zero inventory; three synthetic pools return explicit deltas and ignore callback failure. Actual router code/real factory reads only. No full transaction success claim.')
 Path('reports/amm/router0480-a2-nested.json' if args.a2 else 'reports/amm/router0480-profit-'+str(args.minimum)+'-'+str(args.final_inventory)+'.json' if args.minimum is not None else 'reports/amm/router0480-nested-paid.json' if args.pay_transfers else 'reports/amm/router0480-nested-registration-assumed.json' if args.assume_registration else 'reports/amm/router0480-nested.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(swaps=len(swaps),error=r['error'],calls=r['calls'])))
if __name__=='__main__':main()
