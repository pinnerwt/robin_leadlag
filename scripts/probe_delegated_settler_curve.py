"""Saved V4 curve plus actual manager/hook swap, synthetic unlock caller only."""
import copy,json
from pathlib import Path
from probe_delegated_callback import push
from probe_delegated_kind8 import run
from v4_pool_state import load
from delegated_settler_v4 import first_swap
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'
ROOT='0xe8852602f84e04e284286d8db01a41edd0ccefb0'
def harness(swap):
 unlock=bytes.fromhex('48c89491')+(32).to_bytes(32,'big')+bytes(32)
 def invoke(data,offset):
  return b'\x61'+len(data).to_bytes(2,'big')+b'\x61'+offset.to_bytes(2,'big')+b'\x60\x00\x39'+push(0)+push(0)+push(len(data))+push(0)+push(0)+bytes.fromhex('73'+MANAGER[2:])+b'\x5a\xf1\x50\x00'
 head=b'\x5f\x35'+push(224)+b'\x1c'+push(0x91dd7346)+b'\x14\x61\x00\x00\x57'
 u=invoke(unlock,0);v=b'\x5b'+invoke(swap,0);start=len(head)+len(u)+len(v)
 head=head[:-3]+(len(head)+len(u)).to_bytes(2,'big')+head[-1:]
 return head+invoke(unlock,start)+b'\x5b'+invoke(swap,start+len(unlock))+unlock+swap

def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());rows=[]
 for entry in json.loads(Path('reports/amm/delegated-holder-plans.json').read_text())['transactions']:
  a=first_swap(entry['plan']['actions'][0]['data']);key=dict(currency0=a['currency0'],currency1=a['currency1'],fee=a['fee'],tick_spacing=a['spacing'],hooks=a['hook'])
  expected=None;error=None
  try:
   curve=load(seed['accounts'][MANAGER]['storage'],key);expected=curve.swap(a['zero'],a['amount'],a['limit'])
  except ValueError as exc:error=str(exc)
  s=copy.deepcopy(seed);s['accounts'][ROOT]['code']='0x'+harness(bytes.fromhex(a['swap_calldata'][2:])).hex();s['trace_execution']=True;s['execute_targets']=[ROOT,MANAGER,a['hook']]
  h=seed['anchor'];tx=dict(tx=entry['tx'],to=ROOT,data='0x',sequence=int(h['number'],16),timestamp=int(h['timestamp'],16),l1_block=int(h.get('l1BlockNumber','0x1'),16),**{'from':'0x5399d94d2cab7c252a6034042e1917a0e5e17a18'})
  r=run(s,tx);rows.append(dict(tx=tx,key=key,curve_result=expected,curve_error=error,result=r))
  print(entry['tx'][:14],error,expected,r['error'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
  print([x for x in r['execution_returns'] if x['selector'] in ('0xf3cd914c','0xb47b2fb1')],flush=True)
 Path('reports/amm/delegated-settler-curve.json').write_text(json.dumps(dict(anchor=seed['anchor']['hash'],cases=rows,caveat='Archived checkpoint scenario, synthetic unlock caller. Actual manager/hook code. Funding/settlement incomplete; attempted writes not committed; not historical prestate.'),indent=2)+'\n')
if __name__=='__main__':main()
