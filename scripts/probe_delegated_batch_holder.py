"""Actual saved downstream holder prefix, isolated from synthetic outer funding."""
import argparse,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--settler',action='store_true');args=ap.parse_args()
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True;rows=[]
 for c in json.loads(Path('reports/amm/delegated-batch-full-credit.json').read_text())['cases']:
  call=c['result']['calls'][0];tx=dict(c['tx'],to=call['to'],data=call['data'],**{'from':c['tx']['to']})
  if args.settler:seed['execute_targets']=['0xe8852602f84e04e284286d8db01a41edd0ccefb0']
  r=run(seed,tx);rows.append(dict(tx=tx,result=r));print(tx['tx'][:14],r['error'],[(a['to'],a['data'][:10]) for a in r['calls']],flush=True)
 Path('reports/amm/delegated-batch-'+('settler' if args.settler else 'holder')+'.json').write_text(json.dumps(dict(cases=rows,caveat='Isolated saved-code holder execution with outer router caller. Funding and complete transaction not executed.'),indent=2)+'\n')
if __name__=='__main__':main()
