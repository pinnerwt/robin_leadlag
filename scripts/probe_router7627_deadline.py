"""Timestamp interventions for nine-byte entry format, current code only."""
import json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 code=json.loads(Path('reports/amm/router7627-code.json').read_text());root=code['address'];row=json.loads(Path('reports/amm/router7627-prefix.json').read_text())['cases'][0];tx=row['tx'];deadline=int(tx['data'][2:10],16);accounts={a:dict(balance='0x0',code='0x',storage={}) for a in (tx['from'].lower(),'0x'+'00'*20,row['result']['calls'][0]['to'])};accounts[root]=dict(balance='0x0',code=code['code'],storage={});s=dict(accounts=accounts,trace_execution=True,control_targets=[root],trace_calldata=True);rows=[]
 for delta in (-2,-1,0,1,2):
  t=dict(tx,timestamp=deadline+delta);r=run(s,t);rows.append(dict(timestamp=t['timestamp'],delta=delta,result=r));print(delta,r['error'],r['execution_success'],[(c['data']) for c in r['calls']])
 Path('reports/amm/router7627-deadline.json').write_text(json.dumps(dict(tx=tx,deadline=deadline,cases=rows,caveat='Current code with synthetic timestamp/empty account metadata, intercepted first getter. No historical swap execution.'),indent=2)+'\n')
if __name__=='__main__':main()
