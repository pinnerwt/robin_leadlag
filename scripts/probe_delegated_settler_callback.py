"""Synthetic V4 manager callback in actual holder/settler transient context."""
import argparse,copy,json
from pathlib import Path
from probe_delegated_callback import callback_code
from probe_delegated_funding import manager_code
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=int);ap.add_argument('--fund-take',action='store_true');ap.add_argument('--settle',action='store_true');ap.add_argument('--wrap',action='store_true');ap.add_argument('--v3-output',type=int);args=ap.parse_args()
 if args.v3_output is not None and (not args.wrap or not 0<args.v3_output<1<<127):ap.error('--v3-output requires --wrap and positive int128')
 if args.wrap and not args.settle:ap.error('--wrap requires --settle')
 if args.settle and not args.fund_take:ap.error('--settle requires --fund-take')
 if args.fund_take and args.output is None:ap.error('--fund-take requires --output')
 if args.output is not None and not 0<args.output<1<<127:ap.error('output must fit positive int128')
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True;rows=[]
 for c in json.loads(Path('reports/amm/delegated-batch-settler.json').read_text())['cases']:
  call=c['result']['calls'][0];manager=call['to'];settler=call['caller'];cb=bytes.fromhex('91dd7346'+call['data'][10:]);s=copy.deepcopy(seed)
  s['accounts'][manager]=dict(code='0x'+callback_code(cb,settler).hex(),balance='0x0',nonce='0x0',storage={})
  s['execute_targets']=[settler];s['execute_calls']=[manager+':'+call['data']]
  if args.output is not None:
   prior=json.loads(Path('reports/amm/delegated-settler-callback.json').read_text())
   swap=next(x for x in prior['cases'] if x['tx']['tx']==c['tx']['tx'])['result']['calls'][0]
   raw=bytes.fromhex(swap['data'][10:]);amount=-int.from_bytes(raw[192:224],'big',signed=True)
   delta=(args.output<<128)+((-amount)%(1<<128))
   s['getters']={manager:{swap['data']:'0x'+delta.to_bytes(32,'big').hex()}}
  if args.fund_take:
   prior_take=json.loads(Path('reports/amm/delegated-settler-output-'+str(args.output)+'.json').read_text())
   take=next(x for x in prior_take['cases'] if x['tx']['tx']==c['tx']['tx'])['result']['calls'][0]
   s['accounts'][manager]['code']='0x'+manager_code(cb,settler).hex()
   s['accounts'][manager]['balance']=hex(args.output)
   s['execute_calls'].append(manager+':'+take['data'])
  r=run(s,c['tx']);stages=[r]
  if args.settle:
   for _ in range(16):
    if r['error'] or len(r['calls'])!=1:break
    pending=r['calls'][0];selector=pending['data'][:10];reply=None
    if pending['to']==manager and selector=='0xa5841194':reply='0x'
    elif pending['to']==manager and selector=='0x11da60b4':reply='0x'+amount.to_bytes(32,'big').hex()
    elif selector=='0x23b872dd' and pending['to']==('0x'+raw[44:64].hex()):reply='0x'+(1).to_bytes(32,'big').hex()
    elif args.wrap and pending['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and selector=='0xd0e30db0':reply='0x'
    elif args.wrap and pending['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and selector=='0x70a08231':reply='0x'+args.output.to_bytes(32,'big').hex()
    elif args.v3_output is not None and pending['to']=='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca' and selector=='0x128acb08':
     d=bytes.fromhex(pending['data'][10:]);value=int.from_bytes(d[64:96],'big');reply='0x'+value.to_bytes(32,'big').hex()+((-args.v3_output)%(1<<256)).to_bytes(32,'big').hex()
    elif args.v3_output is not None and pending['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and selector=='0x70a08231':reply='0x'+args.v3_output.to_bytes(32,'big').hex()
    elif pending['to']==c['tx']['to']:
     key=pending['to']+':'+pending['data']
     if key in s['execute_calls']:break
     s['execute_calls'].append(key)
    else:break
    if reply is not None:
     entries=s['getters'].setdefault(pending['to'],{})
     if pending['data'] in entries:break
     entries[pending['data']]=reply
    r=run(s,c['tx']);stages.append(r)
  rows.append(dict(tx=c['tx'],callback='0x'+cb.hex(),synthetic_output=args.output,synthetic_v3_output=args.v3_output,synthetic_native_funding=args.fund_take,synthetic_getters=s.get('getters',{}),execute_calls=s['execute_calls'],stages=stages,result=r))
  print(c['tx']['tx'][:14],r['error'],[(a['to'],a['data'][:10]) for a in r['calls']],flush=True)
 Path('reports/amm/delegated-settler-'+('tail-'+str(args.output)+'-'+str(args.v3_output) if args.v3_output is not None else 'wrapped-'+str(args.output) if args.wrap else 'settled-'+str(args.output) if args.settle else 'funded-'+str(args.output) if args.fund_take else 'output-'+str(args.output) if args.output is not None else 'callback')+'.json').write_text(json.dumps(dict(cases=rows,caveat='Synthetic manager callback ignores callback failure and does not settle. Actual holder/settler code and transient context retained; no complete execution claim.'),indent=2)+'\n')
if __name__=='__main__':main()
