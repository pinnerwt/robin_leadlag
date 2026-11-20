"""Historical calldata against separately captured current code; no state claims."""
import json,re
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 code=json.loads(Path('reports/amm/router7627-code.json').read_text());root=code['address'];rows=[]
 for line in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines():
  tx=json.loads(line)['tx']
  if (tx.get('to') or '').lower()!=root:continue
  accounts={a:dict(balance='0x0',code='0x',storage={}) for a in (tx['from'].lower(),'0x'+'00'*20)};accounts[root]=dict(balance='0x0',code=code['code'],storage={});seed=dict(accounts=accounts,trace_execution=True,trace_calldata=True,control_targets=[root]);r=run(seed,tx);baseline=r;synthetic=[]
  if r['error'] and (m:=re.search(r'unknown account (0x[0-9a-fA-F]{40})',r['error'])):
   address=m.group(1).lower();accounts[address]=dict(balance='0x0',code='0x',storage={});synthetic.append(address);r=run(seed,tx)
  rows.append(dict(tx=tx,baseline=baseline,synthetic_account_metadata=synthetic,result=r));print(tx['tx'][:12],r['error'],r['calls'])
 Path('reports/amm/router7627-prefix.json').write_text(json.dumps(dict(code_anchor=code['anchor']['number'],code_hash=code['code_hash'],cases=rows,caveat='New code with archived calldata, synthetic empty caller metadata; root storage absent and never assumed zero. Not historical execution.'),indent=2)+'\n')
if __name__=='__main__':main()
