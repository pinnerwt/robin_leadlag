"""Saved afterSwap hook dependency probe with explicit synthetic pool delta."""
import argparse,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--take-success',action='store_true');args=ap.parse_args()
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True;rows=[]
 for c in json.loads(Path('reports/amm/delegated-settler-callback.json').read_text())['cases']:
  call=c['result']['calls'][0];raw=bytes.fromhex(call['data'][10:]);hook='0x'+raw[140:160].hex()
  amount=-int.from_bytes(raw[192:224],'big',signed=True);output=10**15;delta=(output<<128)+((-amount)%(1<<128));w=lambda n:n.to_bytes(32,'big')
  data='0xb47b2fb1'+(w(int(call['caller'],16))+raw[:256]+w(delta)+w(352)+w(0)).hex()
  tx=dict(c['tx'],to=hook,data=data,**{'from':call['to']});r=run(seed,tx);getters={}
  if args.take_success and not r['error'] and len(r['calls'])==1:
   take=r['calls'][0]
   if take['data'].startswith('0x0b0d9c09'):
    getters={take['to']:{take['data']:'0x'}};seed['getters']=getters;r=run(seed,tx);seed.pop('getters')
  rows.append(dict(tx=tx,synthetic_output=output,synthetic_delta=delta,synthetic_getters=getters,result=r))
  print(tx['tx'][:14],r['error'],[(a['to'],a['data'][:10]) for a in r['calls']],flush=True)
 Path('reports/amm/delegated-settler-hook'+('-take-success' if args.take_success else '')+'.json').write_text(json.dumps(dict(cases=rows,caveat='Saved hook code/storage, synthetic pre-hook pool output. Isolated afterSwap call, not manager execution or complete historical state.'),indent=2)+'\n')
if __name__=='__main__':main()
