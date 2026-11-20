"""Startup-only reuse of complete trie nodes after same-root proof at a new anchor."""
import argparse,json
from pathlib import Path
from bootstrap_state import Bootstrap
from audit_storage_trie import audit

def repin(known,head,proof):
 old=audit(known)
 if not old['complete']:raise ValueError('source trie incomplete')
 if proof['address'].lower()!=old['account'].lower() or proof['storageHash']!=old['storage_root']:raise ValueError('storage root/account changed; recollect trie')
 p=dict(proof);p['storageProof']=known['proof']['storageProof']
 result=dict(anchor=head,proof=p,reused_from_anchor=known['anchor']['hash'])
 if not audit(result)['complete']:raise ValueError('repinned trie incomplete')
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--anchor',type=Path,required=True);p.add_argument('--proof',type=Path,action='append',required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
 h=json.loads(a.anchor.read_text());b=Bootstrap('https://rpc-robinhood.blockmachine.io',interval=.7);a.output_dir.mkdir(exist_ok=True);manifest=[]
 for path in a.proof:
  known=json.loads(path.read_text());address=known['proof']['address'];v=b.rpc('eth_getProof',[address,[],h['number']]);r=repin(known,h,v);out=a.output_dir/(address.lower()+'.json');out.write_text(json.dumps(r,separators=(',',':'))+'\n');manifest.append(str(out));print('pinned',address,flush=True)
 (a.output_dir/'manifest.json').write_text(json.dumps(dict(anchor=h['hash'],proofs=manifest),indent=2)+'\n')
