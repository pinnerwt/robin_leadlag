"""Offline signer-as-EOA counterfactual; actual ECRECOVER, explicit metadata."""
import argparse,copy,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--funding',action='store_true');ap.add_argument('--full-credit',action='store_true');args=ap.parse_args()
 if args.full_credit and not args.funding:ap.error('--full-credit requires --funding')
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True;rows=[]
 source=json.loads(Path('reports/amm/delegated-batch-allow-signer.json').read_text())
 for c in source['cases']:
  if not c['result']['error']:continue
  tx=c['tx'];s=copy.deepcopy(seed);s['accounts'][tx['to']]['storage'].update(c['synthetic_patches'])
  signer='0x'+bytes.fromhex(tx['data'][10:])[7*32+12:8*32].hex()
  synthetic=[signer,'0x'+'00'*19+'01','0x'+'00'*20]
  for address in synthetic:s['accounts'][address]=dict(code='0x',balance='0x0',nonce='0x0',storage={})
  s['execute_targets']=[synthetic[1]]
  r=run(s,tx);stages=[r];getters={}
  if args.funding:
   for _ in range(6):
    if r.get('error') or not r['calls']:break
    if len(r['calls'])!=1 and not all(call['data'].startswith('0x095ea7b3') for call in r['calls']):break
    call=r['calls'][0];selector=call['data'][:10]
    if selector not in ('0x70a08231','0x23b872dd','0x095ea7b3'):break
    value='0x'+(0 if selector=='0x70a08231' else 1).to_bytes(32,'big').hex()
    if selector=='0x70a08231' and args.full_credit and call['to'].lower()=='0x'+bytes.fromhex(tx['data'][10:])[44:64].hex():
     amount=int.from_bytes(bytes.fromhex(tx['data'][10:])[64:96],'big')
     value=[value,value]+['0x'+amount.to_bytes(32,'big').hex()]*8
    target=getters.setdefault(call['to'],{})
    if call['data'] in target:break
    target[call['data']]=value;s['getters']=getters;r=run(s,tx);stages.append(r)
  rows.append(dict(tx=tx,synthetic_patches=c['synthetic_patches'],synthetic_accounts=synthetic,synthetic_getters=getters,stages=stages,result=r))
  print(tx['tx'][:14],r['error'],r['output'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/delegated-batch-'+('full-credit' if args.full_credit else 'funding' if args.funding else 'signature')+'.json').write_text(json.dumps(dict(cases=rows,caveat='Signer code/balance/nonce not observed: explicit EOA counterfactual. Guard/allowlist changes inherited. Real precompile execution; no pool changes committed.'),indent=2)+'\n')
if __name__=='__main__':main()
