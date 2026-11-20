"""Isolated actual holder/settler prefixes for unpinned batch entry variants."""
import argparse,copy,json,re
from pathlib import Path
from delegated_batch_envelope import inspect as envelope
from delegated_batch_route import router_payload,ROUTER,HOLDER
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--continue-prefix',action='store_true');args=ap.parse_args()
 base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());base['trace_execution']=True;rows=[]
 for entry in json.loads(Path('reports/amm/batch-unpinned-plans.json').read_text())['transactions']:
  seed=copy.deepcopy(base);original=entry['tx'];p=router_payload(envelope(original['data'])['calls'][1]['data']);plan=entry['plan'];seed['execute_targets']=[plan['target']]
  tx=dict(original,to=HOLDER,data=p['payload'],**{'from':ROUTER});r=run(seed,tx);stages=[r];synthetic=[]
  if args.continue_prefix:
   for _ in range(3):
    unknown=re.search(r'unknown account (0x[0-9a-fA-F]{40})',r.get('error') or '')
    if unknown:
     address=unknown[1].lower();seed['accounts'][address]=dict(code='0x',balance='0x0',nonce='0x0',storage={});synthetic.append(address)
    elif len(r['calls'])==1 and r['calls'][0]['to']==HOLDER and r['calls'][0]['data'].startswith('0x15dacbea'):
     call=r['calls'][0];seed.setdefault('execute_calls',[]).append(call['to']+':'+call['data'])
    elif len(r['calls'])==1 and r['calls'][0]['data'].startswith('0x23b872dd'):
     call=r['calls'][0];seed.setdefault('getters',{}).setdefault(call['to'],{})[call['data']]='0x'+(1).to_bytes(32,'big').hex()
    else:break
    r=run(seed,tx);stages.append(r)
  rows.append(dict(tx=tx,original_target=original['to'],entry_code_verified=False,synthetic_accounts=synthetic,synthetic_getters=seed.get('getters',{}),stages=stages,result=r))
  print(tx['tx'][:14],r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/batch-variant-'+('continuation' if args.continue_prefix else 'prefixes')+'.json').write_text(json.dumps(dict(cases=rows,caveat='Isolated saved holder/settler code; original delegated entry and outer execution unverified. No full funding/transaction parity.'),indent=2)+'\n')
if __name__=='__main__':main()
