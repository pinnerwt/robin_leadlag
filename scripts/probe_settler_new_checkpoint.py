"""First upstream pool at its own newly initialized anchor; no RPC."""
import json
from pathlib import Path
from probe_delegated_settler_curve import harness,ROOT,MANAGER
from probe_delegated_kind8 import run
from v4_pool_state import load

def main():
 source=json.loads(Path('reports/amm/settler-upstream-new-checkpoint.json').read_text())
 if not source['anchor_verified'] or source['error']:raise ValueError('unverified initialization')
 seed=source['seed'];a=source['plan'];key=dict(currency0=a['currency0'],currency1=a['currency1'],fee=a['fee'],tick_spacing=a['spacing'],hooks=a['hook'])
 curve_error=None;expected=None
 try:expected=load(seed['accounts'][MANAGER]['storage'],key).swap(a['zero'],a['amount'],a['limit'])
 except ValueError as e:curve_error=str(e)
 origin='0x5399d94d2cab7c252a6034042e1917a0e5e17a18';synthetic=[ROOT,origin,'0x'+'00'*20]
 for address in synthetic:seed['accounts'][address]=dict(code='0x',balance='0x0',nonce='0x0',storage={})
 seed['accounts'][ROOT]['code']='0x'+harness(bytes.fromhex(a['swap_calldata'][2:])).hex();seed['trace_execution']=True;seed['execute_targets']=[ROOT,MANAGER,a['hook']]
 h=seed['anchor'];tx=dict(tx='first-upstream-new-checkpoint',to=ROOT,data='0x',sequence=int(h['number'],16),timestamp=int(h['timestamp'],16),l1_block=int(h.get('l1BlockNumber','0x1'),16),**{'from':origin});r=run(seed,tx)
 Path('reports/amm/settler-upstream-new-probe.json').write_text(json.dumps(dict(anchor=h['hash'],expected=expected,curve_error=curve_error,code_matches=source['code_matches'],synthetic_accounts=synthetic,tx=tx,result=r,caveat='New coherent checkpoint scenario only. Synthetic unlock caller/account metadata; full settlement omitted. Not historical corpus parity.'),indent=2)+'\n')
 print('code matches',source['code_matches']);print('curve',curve_error,expected);print('execution',r['error'],r['calls']);print([x for x in r['execution_returns'] if x['selector'] in ('0xf3cd914c','0xb47b2fb1')])
if __name__=='__main__':main()
