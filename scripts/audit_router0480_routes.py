"""Strict structural route audit; observed log identities are validation only."""
import json
from collections import Counter
from pathlib import Path
from router0480_route import inspect
from router0480_mixed_route import inspect as mixed
from router0480_v4_route import inspect as v4_route
from router0480_two_pool_route import inspect as two_pool
from router0480_0d_route import inspect as route0d
from router0480_first_swap import ROUTER
from amm_feed_state import SWAP

def inspect_route(calldata,v2):
 errors=[]
 for parser in (inspect,lambda data:mixed(data,v2),v4_route,two_pool,route0d):
  try:return parser(calldata)
  except ValueError as exc:errors.append(str(exc))
 raise ValueError('no supported0480 route: '+ '; '.join(errors))

def main():
 metadata=json.loads(Path('reports/amm/router0480-v2-tokens.json').read_text());v2={metadata['pool']:dict(tokens=['0x'+metadata['getters'][k]['output'][-40:] for k in ('token0','token1')])}
 pools={p['pool'] for p in json.loads(Path('captures/startup-v9-quotes.json').read_text())['pools']};rows=[]
 for line in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines():
  source=json.loads(line);tx=source['tx']
  if (tx.get('to') or '').lower()!=ROUTER:continue
  observed=sorted({l['address'].lower() for l in source['logs'] if l.get('topics',[None])[0]==SWAP and l['address'].lower() in pools})
  try:
   plan=inspect_route(tx['data'],v2)
   recorded=sorted(set(plan['pools'])&pools);rows.append(dict(tx=tx['tx'],plan=plan,error=None,observed_recorded_pools=observed,decoded_recorded_pools=recorded,unexplained=sorted(set(observed)-set(recorded)),safe_to_skip=False))
  except ValueError as exc:rows.append(dict(tx=tx['tx'],error=str(exc),observed_recorded_pools=observed,safe_to_skip=False))
 report=dict(rows=rows,counts=dict(Counter('structural_route' if x['error'] is None else x['error'] for x in rows)),caveat='Structural command scope only. Callback profiles, full numeric state and lifecycle remain unverified; no production coverage promotion.')
 Path('reports/amm/router0480-route-corpus.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(counts=report['counts'],unexplained=[r['tx'] for r in rows if r.get('unexplained')]),indent=2))
if __name__=='__main__':main()
