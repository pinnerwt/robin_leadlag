"""Synthetic V3 pool calls actual settler payment callback then returns deltas."""
import argparse,copy,json
from pathlib import Path
from probe_delegated_callback import push
from probe_delegated_funding import manager_code
from probe_delegated_kind8 import run

def pool_code(callback,recipient,reply):
 prefix=push(len(callback))+b'\x61\x00\x00'+push(0)+b'\x39'
 prefix+=push(0)+push(0)+push(len(callback))+push(0)+push(0)+bytes.fromhex('73'+recipient[2:])+b'\x5a\xf1\x50'
 for i in range(0,len(reply),32):prefix+=b'\x7f'+reply[i:i+32]+push(i)+b'\x52'
 prefix+=push(len(reply))+push(0)+b'\xf3'
 at=len(push(len(callback)))+1
 return prefix[:at]+len(prefix).to_bytes(2,'big')+prefix[at+2:]+callback

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=int);ap.add_argument('--pay-tail',action='store_true');args=ap.parse_args()
 if args.pay_tail and args.output is None:ap.error('--pay-tail requires --output')
 if args.output is not None and not 0<args.output<1<<127:ap.error('output bounds')
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True
 c=json.loads(Path('reports/amm/delegated-settler-tail-796969091046830-1454595.json').read_text())['cases'][1];s=copy.deepcopy(seed);tx=c['tx'];manager='0x8366a39cc670b4001a1121b8f6a443a643e40951';settler='0xe8852602f84e04e284286d8db01a41edd0ccefb0';pool='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
 s['accounts'][manager]=dict(code='0x'+manager_code(bytes.fromhex(c['callback'][2:]),settler).hex(),balance=hex(c['synthetic_output']),nonce='0x0',storage={})
 s['getters']=c['synthetic_getters'];s['execute_calls']=c['execute_calls'];s['execute_targets']=[settler]
 data,reply=next(iter(s['getters'].pop(pool).items()));d=bytes.fromhex(data[10:]);offset=int.from_bytes(d[128:160],'big');n=int.from_bytes(d[offset:offset+32],'big');opaque=d[offset+32:offset+32+n];word=lambda x:x.to_bytes(32,'big')
 if args.output is not None:
  c['synthetic_v3_output']=args.output;reply=reply[:66]+((-args.output)%(1<<256)).to_bytes(32,'big').hex()
 cb=bytes.fromhex('fa461e33')+bytes.fromhex(reply[2:])+word(96)+word(n)+opaque+bytes((-n)%32)
 s['accounts'][pool]['code']='0x'+pool_code(cb,settler,bytes.fromhex(reply[2:])).hex();s['execute_calls'].append(pool+':'+data)
 r=run(s,tx);stages=[r]
 # Permit only the callback's explicit WETH transfer to the synthetic pool.
 for _ in range(5 if args.pay_tail else 2):
  if r['error'] or len(r['calls'])!=1:break
  call=r['calls'][0]
  if call['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73' and call['data'][:10]=='0xa9059cbb':value=1
  elif call['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and call['data'][:10]=='0x70a08231':value=c['synthetic_v3_output']
  elif args.pay_tail and call['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168' and call['data'][:10]=='0xa9059cbb':value=1
  else:break
  if args.pay_tail and call['data'][:10]=='0x70a08231':
   plan=json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions'][1]['plan'];tail=bytes.fromhex(plan['actions'][3]['data'][10:]);threshold=int.from_bytes(tail[64:96],'big')
   value=['0x'+word(value).hex(),'0x'+word(value-max(0,value-1-threshold)).hex()]
  s['getters'].setdefault(call['to'],{})[call['data']]=value if isinstance(value,list) else '0x'+word(value).hex();r=run(s,tx);stages.append(r)
 Path('reports/amm/delegated-settler-tail-callback'+('-output-'+str(args.output) if args.output is not None else '')+('-paid' if args.pay_tail else '')+'.json').write_text(json.dumps(dict(tx=tx,synthetic_v3_output=c['synthetic_v3_output'],synthetic_callback='0x'+cb.hex(),synthetic_getters=s['getters'],stages=stages,result=r,caveat='Synthetic manager and pool. V3 callback executes actual settler, but synthetic pool ignores callback success. No full execution claim.'),indent=2)+'\n')
 print(r['error'],r['execution_success'],r['output'],[(a['to'],a['data'][:10]) for a in r['calls']])
if __name__=='__main__':main()
