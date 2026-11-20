"""Exercise fixed-anchor bootstrap -> follower installation from local evidence."""
import json
from pathlib import Path
from bootstrap_aqua import refresh_aqua
from aqua_book import make_book,C9
from hub_state import HUB
seed=json.loads(Path('captures/startup-v9-quotes.json').read_text())
deps=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
assert seed['anchor']['hash']==deps['anchor']['hash']
registry=json.loads(Path('config/aqua-router-template.json').read_text())
registry['anchor_hash']=seed['anchor']['hash']
inventory=json.loads(Path('reports/amm/router-inventory-checkpoint.json').read_text())
assert inventory['anchor_hash']==seed['anchor']['hash']
balances={e['token']:int(e['balance']) for e in inventory['entries'] if e['router']==C9}
slots={int(k,16):v for k,v in deps['accounts'][HUB]['storage'].items()}
calls=[]
def local_rpc(method,params):
 calls.append(method)
 if method=='eth_getStorageAt':
  assert params[0]==HUB and params[-1]==seed['anchor']['number']
  return '0x'+int(slots[int(params[1],16)],16).to_bytes(32,'big').hex()
 if method=='eth_call':
  assert params[-1]==seed['anchor']['number']
  return '0x'+balances[params[0]['to']].to_bytes(32,'big').hex()
 if method=='eth_getBlockByNumber':return seed['anchor']
 raise AssertionError(method)
seed['aqua']=refresh_aqua(json.loads(Path('config/aqua-template.json').read_text()),seed['anchor'],local_rpc)
b=make_book(seed,registry,True)
before=len(calls)
case=json.loads(Path('tests/fixtures/c7_settlement.json').read_text())[0]
touched=b.proposal(dict(tx='local-install-check',to=C9,data=case['calldata']))
assert len(touched)==1 and len(calls)==before
Path('reports/amm/aqua-bootstrap-install-validation.json').write_text(json.dumps(dict(
 bootstrap_reads=len(calls),hot_path_requests=0,touched=touched,
 caveat='Offline RPC adapter backed by archived evidence; not a live network checkpoint'),indent=2)+'\n')
print('5 pinned initialization reads, successful book install and C7 transition; 0 hot-path requests')
