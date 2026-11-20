"""Local direct swaps on one coherent dependency anchor, no RPC or logs."""
import argparse,json,subprocess,tempfile
from pathlib import Path
from bootstrap_state import word,unpack
from bootstrap_index4_observations import POOL
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('seed');ap.add_argument('observations');ap.add_argument('--settlement-probe',action='store_true');a=ap.parse_args()
s=json.load(open(a.seed));o=json.load(open(a.observations))
if s['anchor']['hash']!=o['anchor']['hash']:raise ValueError('anchor mismatch')
s.update(trace_execution=True,trace_hashes=True)
s['execute_targets']=['0x27d5eb73e7406675f6b0cbd037490ec3dba935a4','0xcc421483cd131a8fd6b68c37e46f244dbec4f797','0xf437f62053acb121665b8fdbfea8f214fb8e589d','0x382409fad8503fbcdbb27a4211551fa03e884078','0xdd1705e23762f4d6e44d8c31bd8ea80c54612239',POOL,'0xc0ed888afe87ed1acf01d9f19bb850159e3ce434','0xc63d7338c178e805c544b8f897066bd3bbcbe136','0xaa48aaef655fb7cd7acc04717f66022a4771a345']
s['delegate_targets']=['0x1642634c8cb1c9f1b84c9a1a08534f8c3f4e89f8','0x1ad7a8703ebff81c0d753190938f228672ec7e42']
if a.settlement_probe:
 prior=json.load(open('reports/amm/routera3d-index4-fresh-local-probe.json'))
 if prior['anchor']['hash']!=s['anchor']['hash']:raise ValueError('prefix anchor mismatch')
 s['getters']={}
 for result in prior['results']:
  for call in result['calls']:
   if call['data'].startswith('0xa9059cbb'):
    s['getters'].setdefault(call['to'],{})[call['data']]='0x'+word(1).hex()
    output=int(call['data'][-64:],16)
    buy=call['to']=='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
    deltas=(-output,16777216) if buy else (10**16,-output)
    callback='0xfa461e33'+b''.join(word(v) for v in [*deltas,96,0]).hex()
    s['getters'].setdefault('0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880',{})[callback]='0x'
 for token,amount in [('0x0bd7d308f8e1639fab988df18a8011f41eacad73',10**16),('0x5fc5360d0400a0fd4f2af552add042d716f1d168',16777216)]:
  s['getters'].setdefault(token,{})['0x70a08231'+word(int(POOL,16)).hex()]=['0x'+word(0).hex(),'0x'+word(amount).hex()]
head=s['anchor'];sqrt=unpack(o['slot0'])[0];caller='0xe3c90972c6462bb4a4c75cf49dcf4189c5b42880';txs=[]
for zero,amount in [(False,16777216),(True,10**16)]:
 limit=sqrt*999//1000 if zero else sqrt*1001//1000
 data='0x128acb08'+b''.join(word(v) for v in [int(caller,16),int(zero),amount,limit,160,0]).hex()
 txs.append(dict(tx='fresh-index4-'+str(zero),to=POOL,data=data,sequence=int(head['number'],16),timestamp=int(head['timestamp'],16),l1_block=int(head.get('l1BlockNumber','0x1'),16),**{'from':caller}))
with tempfile.NamedTemporaryFile(suffix='.json') as tmp:
 Path(tmp.name).write_text(json.dumps(s));rows=list(map(json.loads,subprocess.check_output(['target/release/examples/router_prefix',tmp.name],input=''.join(json.dumps(t)+'\n' for t in txs),text=True).splitlines()))
Path('reports/amm/routera3d-index4-fresh-'+('settlement' if a.settlement_probe else 'local')+'-probe.json').write_text(json.dumps(dict(anchor=head,transactions=txs,results=rows,caveat='Synthetic transfer/payment replies; isolated pool arithmetic only.' if a.settlement_probe else 'Unfunded direct pool calls; prefix only, no success/commit claim.'),indent=2)+'\n')
for r in rows:print(r['tx'],r['error'],r['execution_success'],[(c['to'],c['data'][:10]) for c in r['calls']])
