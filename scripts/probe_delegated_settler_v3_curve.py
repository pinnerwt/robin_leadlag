"""Actual downstream V3 prefix compared with local checkpoint curve, no network."""
import argparse,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--settle',action='store_true');args=ap.parse_args()
 preview=json.loads(Path('reports/amm/delegated-settler-chain-preview.json').read_text());seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 if seed['anchor']['hash']!=preview['anchor']:raise ValueError('anchor mismatch')
 source=json.loads(Path('reports/amm/delegated-settler-wrapped-'+str(preview['v4_net'])+'.json').read_text())
 c=next(c for c in source['cases'] if c['tx']['tx']==preview['tx']);call=c['result']['calls'][0]
 h=seed['anchor'];tx=dict(c['tx'],to=call['to'],data=call['data'],timestamp=int(h['timestamp'],16),sequence=int(h['number'],16),**{'from':call['caller']})
 seed['trace_execution']=True;r=run(seed,tx);stages=[r];getters={}
 if args.settle:
  for _ in range(4):
   if r['error'] or len(r['calls'])!=1:break
   pending=r['calls'][0];sel=pending['data'][:10]
   if sel=='0xa9059cbb' and pending['to']=='0x5fc5360d0400a0fd4f2af552add042d716f1d168':value='0x'+(1).to_bytes(32,'big').hex()
   elif sel=='0x70a08231' and pending['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73':value=['0x'+bytes(32).hex(),'0x'+preview['v3_intent']['amount'].to_bytes(32,'big').hex()]
   elif pending['to'].lower()==tx['from'].lower() and sel=='0xfa461e33':value='0x'
   else:break
   entries=getters.setdefault(pending['to'],{})
   if pending['data'] in entries:break
   entries[pending['data']]=value;seed['getters']=getters;r=run(seed,tx);stages.append(r)
 report=dict(anchor=h['hash'],tx=tx,expected=preview['v3_fill'],synthetic_getters=getters,stages=stages,result=r,caveat='Actual saved pool code/state, isolated swap prefix at checkpoint. No successful settlement or historical prestate claim; unknown storage not substituted.')
 Path('reports/amm/delegated-settler-v3-curve'+('-settled' if args.settle else '')+'.json').write_text(json.dumps(report,indent=2)+'\n')
 print(r['error'],[(x['to'],x['data'][:10],x['data'][-64:]) for x in r['calls']]);print(r['storage_writes'])
if __name__=='__main__':main()
