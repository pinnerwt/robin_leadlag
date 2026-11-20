"""Offline outer-router minimum boundary, all other assumptions held fixed."""
import copy,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 full=json.loads(Path('captures/startup-v9-dependencies.json').read_text());source=json.loads(Path('reports/amm/delegated-outer-completion-consumed.json').read_text());tx=source['tx'];usd='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
 addresses={tx['to'].lower(),tx['from'].lower(),*source['synthetic_accounts'],*source['synthetic_getters']}
 seed=dict(anchor=full['anchor'],accounts={a:v for a,v in full['accounts'].items() if a in addresses},trace_execution=True,getters=source['synthetic_getters'],execute_targets=['0x'+'00'*19+'01'])
 seed['accounts'][tx['to']]['storage'].update(source['synthetic_patches'])
 for a in source['synthetic_accounts']:seed['accounts'][a]=dict(code='0x',balance='0x0',nonce='0x0',storage={})
 minimum=int.from_bytes(bytes.fromhex(tx['data'][10:])[96:128],'big');rows=[]
 for amount in (0,minimum-1,minimum,minimum+1):
  s=copy.deepcopy(seed)
  for key in s['getters'][usd]:
   if key.startswith('0x70a08231'):s['getters'][usd][key]=['0x'+bytes(32).hex(),'0x'+amount.to_bytes(32,'big').hex()]
  r=run(s,tx);rows.append(dict(synthetic_usdg_credit=amount,result=r));print(amount,r['error'],r['execution_success'],r['output'],flush=True)
 Path('reports/amm/delegated-outer-minimum.json').write_text(json.dumps(dict(tx=tx,minimum=minimum,cases=rows,caveat='Synthetic successful holder result and balances/profile/signature assumptions. Actual outer code; only output credit varied.'),indent=2)+'\n')
if __name__=='__main__':main()
