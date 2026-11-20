"""Actual saved V2 swap with explicit balances after calldata prefunding/output."""
import argparse,json
from pathlib import Path
from probe_delegated_kind8 import run
from router0480_mixed_route import inspect

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input',type=int);args=ap.parse_args()
 meta=json.loads(Path('reports/amm/router0480-v2-tokens.json').read_text());tokens=['0x'+meta['getters'][k]['output'][-40:] for k in ('token0','token1')];old=json.loads(Path('reports/amm/router0480-a4.json').read_text())['tx'];plan=inspect(old['data'],{meta['pool']:dict(tokens=tokens)});pair=plan['swaps'][2]
 if args.input is not None:pair['input_amount']=args.input
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());keep=set(tokens+[pair['pool'],old['to'].lower(),'0x'+'00'*20,old['from'].lower()]);seed['accounts']={a:v for a,v in seed['accounts'].items() if a in keep};seed.update(trace_execution=True,math_targets=[pair['pool']],control_targets=[pair['pool']],getters={});slot=int(seed['accounts'][pair['pool']]['storage']['0x8'],16);reserves=[slot&((1<<112)-1),(slot>>112)&((1<<112)-1)];balances=[reserves[0]+pair['input_amount']-pair['amount0_out'],reserves[1]-pair['amount1_out']];h=seed['anchor'];tx=dict(old,to=pair['pool'],data=pair['data'],timestamp=int(h['timestamp'],16),sequence=int(h['number'],16),**{'from':old['to'].lower()});stages=[];synthetic=[]
 for _ in range(5):
  r=run(seed,tx);stages.append(r)
  if r['error'] or len(r['calls'])!=1:break
  c=r['calls'][0]
  if c['to'] not in tokens:break
  if c['data'].startswith('0xa9059cbb'):value=1
  elif c['data'].startswith('0x70a08231'):value=balances[tokens.index(c['to'])]
  else:break
  if c['data'] in seed['getters'].get(c['to'],{}):break
  seed['getters'].setdefault(c['to'],{})[c['data']]='0x'+value.to_bytes(32,'big').hex();synthetic.append(dict(call=c,value=value))
 Path('reports/amm/router0480-v2-curve.json' if args.input is None else 'reports/amm/router0480-v2-curve-input-'+str(args.input)+'.json').write_text(json.dumps(dict(tx=tx,anchor=h['hash'],reserves=reserves,balances=balances,plan=pair,synthetic=synthetic,stages=stages,result=r,caveat='Actual pair code and saved state, explicit token transfer success and balance-credit assumptions. No historical transaction proof.'),indent=2)+'\n');print(json.dumps(dict(error=r['error'],success=r['execution_success'],output=r['output'],calls=r['calls'],writes=r['storage_writes'])))
if __name__=='__main__':main()
