"""Attach complete hashed storage only after proof and same-anchor verification."""
import argparse,copy,json
from pathlib import Path
from audit_storage_trie import audit
from bootstrap_state import hashhex

def attach(seed,proof):
 if seed['anchor']['hash']!=proof['anchor']['hash'] or seed['anchor']['number']!=proof['anchor']['number']:raise ValueError('different checkpoint anchors')
 r=audit(proof)
 if not r['complete']:raise ValueError('incomplete trie')
 address=r['account'].lower();account=seed['accounts'][address];actual=r['proven_account']
 for field in ('balance','nonce'):
  value=account.get(field,0);value=int(value,16) if isinstance(value,str) else value
  if value!=int(actual[field],16):raise ValueError('account metadata disagreement: '+field)
 if hashhex(bytes.fromhex(account.get('code','0x')[2:]))!=actual['code_hash']:raise ValueError('account code disagreement')
 for k,v in account.get('storage',{}).items():
  hashed=hashhex(int(k,16).to_bytes(32,'big'))
  if int(r['hashed_storage'].get(hashed,'0x0'),16)!=int(v,16):raise ValueError('explicit storage disagreement')
 result=copy.deepcopy(seed);a=result['accounts'][address];a['complete_hashed_storage']=r['hashed_storage'];a['verified_storage_root']=r['storage_root']
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('checkpoint',type=Path);p.add_argument('proof',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 out=attach(json.loads(a.checkpoint.read_text()),json.loads(a.proof.read_text()));a.output.write_text(json.dumps(out,separators=(',',':'))+'\n')
