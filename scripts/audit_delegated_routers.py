"""Group unresolved transactions by saved EIP-7702 delegation code.
Identity grouping only: no claim of decoded execution or irrelevant pool scope.
"""
import json
from collections import Counter
from pathlib import Path

def target(code):
 raw=bytes.fromhex(code.removeprefix('0x'))
 return '0x'+raw[3:].hex() if len(raw)==23 and raw[:3]==bytes.fromhex('ef0100') else None

def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text())
 scope=json.loads(Path('reports/amm/swap-scope-audit.json').read_text())
 pending={r['tx'] for r in scope['transactions'] if r['status']=='recorded_pool_unresolved'}
 groups={};txs=[]
 for row in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()):
  tx=row['tx'];account=(tx['to'] or '').lower()
  if tx['tx'] not in pending:continue
  delegate=target(seed['accounts'].get(account,{}).get('code','0x'))
  if delegate is None:continue
  code=seed['accounts'].get(delegate,{})
  group=groups.setdefault(delegate,dict(code_hash=code.get('codeHash'),code_available=bool(code.get('code')),accounts=set(),selectors=Counter(),transactions=[]))
  group['accounts'].add(account);group['selectors'][tx['data'][:10]]+=1;group['transactions'].append(tx['tx']);txs.append(tx)
 for group in groups.values():group['accounts']=sorted(group['accounts'])
 report=dict(anchor=seed['anchor']['hash'],groups=groups,transactions=len(txs),caveat='Saved delegation identities only; current/historical authorization changes and internal swaps not yet replayed.')
 Path('reports/amm/delegated-router-audit.json').write_text(json.dumps(report,indent=2)+'\n')
 Path('reports/amm/delegated-router-txs.jsonl').write_text(''.join(json.dumps(t)+'\n' for t in txs))
 print(json.dumps({a:dict(accounts=len(g['accounts']),transactions=len(g['transactions']),selectors=g['selectors']) for a,g in groups.items()},indent=2))
if __name__=='__main__':main()
