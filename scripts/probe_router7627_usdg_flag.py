"""Offline USDG flag-getter identification; explicit storage interventions only."""
import copy,json,subprocess,re
from pathlib import Path
from bootstrap_state import mapping
from probe_delegated_kind8 import run
from router7627_second_leg import ROUTER
from router7627_credit import USDG

def main():
 base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());source=json.loads(Path('reports/amm/router7627-prefix.json').read_text())['cases'][0]['tx']
 proxy='0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc';impl='0x'+int(base['accounts'][USDG]['storage'][proxy],16).to_bytes(20,'big').hex()
 slot=mapping(int(ROUTER,16),6);cases=[]
 for signature in ('transfer(address,uint256)',):
  selector='0xa9059cbb'
  for value in (None,0,1,256):
   seed=dict(base,accounts={a:copy.deepcopy(base['accounts'][a]) for a in (USDG,impl,'0x'+'00'*20)},delegate_targets=[impl],trace_execution=True,trace_hashes=True)
   sender=ROUTER;seed['accounts'][sender]=dict(code='0x',balance='0x0',storage={})
   if slot in seed['accounts'][USDG]['storage']:raise ValueError('refuse to overwrite known slot')
   if value is not None:seed['accounts'][USDG]['storage'][slot]=hex(value)
   tx=dict(source,to=USDG,data=selector+int('8366a39cc670b4001a1121b8f6a443a643e40951',16).to_bytes(32,'big').hex()+(1).to_bytes(32,'big').hex(),**{'from':ROUTER});result=run(seed,tx)
   cases.append(dict(signature=signature,synthetic_flag=value,result=result));print(signature,value,result['error'],result['output'])
 Path('reports/amm/router7627-usdg-transfer-flag.json').write_text(json.dumps(dict(anchor=base['anchor']['number'],slot=slot,cases=cases,caveat='Offline getter identification. Synthetic flag values do not establish historical status; synthetic empty sender metadata.'),indent=2)+'\n')
if __name__=='__main__':main()
