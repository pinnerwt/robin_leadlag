"""Offline identification of deposit's missing slot via actual balanceOf code."""
import copy,json
from pathlib import Path
from probe_delegated_kind8 import run
from router7627_second_leg import ROUTER

def main():
 base=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 token='0x0bd7d308f8e1639fab988df18a8011f41eacad73';impl='0xc6b81b429797e0f555440b70cd99e032d7ae947e'
 source=json.loads(Path('reports/amm/router7627-prefix.json').read_text())['cases'][0]['tx']
 seed=dict(base,accounts={a:copy.deepcopy(base['accounts'][a]) for a in (token,impl)},delegate_targets=[impl],trace_execution=True,trace_hashes=True)
 sender=source['from'].lower();seed['accounts'][sender]=dict(code='0x',balance='0x0',storage={})
 tx=dict(source,to=token,data='0x70a08231'+int(ROUTER,16).to_bytes(32,'big').hex())
 result=run(seed,tx)
 Path('reports/amm/router7627-weth-balance-slot.json').write_text(json.dumps(dict(tx=tx,result=result,anchor=base['anchor']['number'],synthetic_sender_metadata=sender,caveat='Offline getter dependency identification; missing storage remains an error. No actual balance inferred.'),indent=2)+'\n')
 print(result['error']);print(result['hash_preimages'])
if __name__=='__main__':main()
