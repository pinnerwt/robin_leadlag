"""Synthetic slot0 price intervention, no remote reads or historical parity."""
import argparse,json,re
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--v4-price",type=int);ap.add_argument("--liquidity",type=int);ap.add_argument("--v3-price",type=int,default=3384945089467101610466034);args=ap.parse_args()
 code=json.loads(Path('reports/amm/router7627-code.json').read_text());root=code['address'];old=json.loads(Path('reports/amm/router7627-prefix.json').read_text());rows=[]
 for row in old['cases']:
  tx=row['tx'];call=row['result']['calls'][0];accounts={a:dict(balance='0x0',code='0x',storage={}) for a in (tx['from'].lower(),'0x'+'00'*20,call['to'])};accounts[root]=dict(balance='0x0',code=code['code'],storage={});price=args.v3_price;seed=dict(accounts=accounts,trace_execution=True,trace_calldata=True,control_targets=[root],getters={call['to']:{call['data']:'0x'+price.to_bytes(32,'big').hex()+bytes(192).hex()}});stages=[];assumed=[]
  for _ in range(8):
   r=run(seed,tx);stages.append(r)
   if r['error'] and (m:=re.search(r'unknown account (0x[0-9a-fA-F]{40})',r['error'])):
    address=m.group(1).lower();accounts[address]=dict(balance='0x0',code='0x',storage={});assumed.append(address);continue
   if args.v4_price is not None and len(r['calls'])==1 and r['calls'][0]['data']=='0x1e2eaeafa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8':
    c=r['calls'][0];seed['getters'].setdefault(c['to'],{})[c['data']]='0x'+args.v4_price.to_bytes(32,'big').hex();continue
   if args.liquidity is not None and r['calls']:
    changed=False
    for c in r['calls']:
     value=100 if c['data']=='0xddca3f43' else args.liquidity if c['data'] in ('0x1a686502','0x1e2eaeafa652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782adb') else None
     if value is not None:seed['getters'].setdefault(c['to'],{})[c['data']]='0x'+value.to_bytes(32,'big').hex();changed=True
    if changed:continue
   break
  rows.append(dict(tx=tx,synthetic_price=price,synthetic_accounts=assumed,stages=stages,result=r));print(tx['tx'][:12],r['error'],[(c['to'],c['data']) for c in r['calls']])
 Path('reports/amm/router7627-prices'+('' if args.v3_price==3384945089467101610466034 else '-v3-'+str(args.v3_price))+('' if args.v4_price is None else '-v4-'+str(args.v4_price))+('' if args.liquidity is None else '-liq-'+str(args.liquidity))+'.json').write_text(json.dumps(dict(synthetic_liquidity=args.liquidity,synthetic_v4_price=args.v4_price,code_anchor=code['anchor']['number'],cases=rows,caveat='Synthetic first slot0 price and empty account metadata, current code against archived calldata. No curve state or historical success claim.'),indent=2)+'\n')
if __name__=='__main__':main()
