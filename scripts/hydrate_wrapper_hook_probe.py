"""Bounded initialization-only fixed-anchor hook storage discovery, never hot path."""
import argparse,json,re
from pathlib import Path
from bootstrap_state import Bootstrap
from probe_delegated_kind8 import run

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--sender-disabled',action='store_true');args=ap.parse_args()
 source=json.loads(Path('reports/amm/delegated-wrapper-hook-probe.json').read_text())
 if args.sender_disabled:
  saved=json.loads(Path('reports/amm/delegated-wrapper-hook-initialized-probe.json').read_text())
  source={'seed':saved['seed'],'tx':saved['tx']}
  patch=json.loads(Path('reports/amm/delegated-wrapper-hook-sender-disabled.json').read_text())['synthetic_patch']
  source['seed']['accounts'][source['tx']['to']]['storage'][patch]='0x0'
  source['result']=run(source['seed'],source['tx'])
 seed=source['seed'];tx=source['tx'];anchor=seed['anchor'];b=Bootstrap('https://rpc-robinhood.blockmachine.io');reads=[];stages=[source['result']];error=None
 try:
  for _ in range(12):
   r=stages[-1];match=re.search(r'unknown slot (0x[0-9a-fA-F]+) (0x[0-9a-fA-F]+)',r.get('error') or '')
   if not match:break
   address,slot=match[1].lower(),hex(int(match[2],16))
   if address not in seed['accounts']:break
   value=b.rpc('eth_getStorageAt',[address,slot,anchor['number']]);reads.append(dict(address=address,slot=slot,value=value));seed['accounts'][address].setdefault('storage',{})[slot]=value
   r=run(seed,tx);stages.append(r);print(slot,r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
  verified=b.rpc('eth_getBlockByNumber',[anchor['number'],False])['hash']==anchor['hash']
 except Exception as exc:error=str(exc);verified=False;print(error,flush=True)
 Path('reports/amm/delegated-wrapper-hook-'+('sender-disabled-initialized' if args.sender_disabled else 'initialized-probe')+'.json').write_text(json.dumps(dict(synthetic_sender_disabled=args.sender_disabled,seed=seed,tx=tx,reads=reads,stages=stages,anchor_verified=verified,error=error,
  caveat='Initialization-only bounded storage reads at new code anchor. Scenario uses synthetic amount; incomplete until remaining dependencies resolved.'),indent=2)+'\n')
if __name__=='__main__':main()
