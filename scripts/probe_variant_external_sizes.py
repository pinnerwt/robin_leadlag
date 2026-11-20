"""Offline size sweep against the isolated new-checkpoint swap bytecode."""
import copy,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 prior=json.loads(Path('reports/amm/variant-external-output.json').read_text());rows=[]
 for amount in (10**12,10**15,10**18,10**20):
  s=copy.deepcopy(prior['seed']);s['getters']={};tx=dict(prior['tx']);d=bytes.fromhex(tx['data'][2:]);tx['data']='0x'+(d[:4]+amount.to_bytes(32,'big')+d[36:]).hex();stages=[]
  for _ in range(4):
   r=run(s,tx);stages.append(r)
   if len(r['calls'])!=1:break
   c=r['calls'][0]
   if c['data'].startswith('0x23b872dd'):value='0x'+(1).to_bytes(32,'big').hex()
   elif c['data']=='0x' and c['to']==tx['from']:value='0x'
   else:break
   s['getters'].setdefault(c['to'],{})[c['data']]=value
  rows.append(dict(amount=amount,stages=stages,result=r,synthetic_getters=s['getters']))
  print(amount,r.get('error'),r['execution_success'],r.get('output'),r['calls'])
 Path('reports/amm/variant-external-sizes.json').write_text(json.dumps(dict(anchor=prior['seed']['anchor']['hash'],cases=rows,caveat='Offline new-checkpoint size sweep with mocked token payment and native recipient acceptance.'),indent=2)+'\n')
if __name__=='__main__':main()
