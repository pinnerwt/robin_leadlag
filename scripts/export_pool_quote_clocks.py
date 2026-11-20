"""Quote pools at local state updates and independent one-second expiry ticks.
Never gate pool clock observations on the reference venue's freshness or ticks.
"""
import json,concurrent.futures
from pathlib import Path
import causal_spcx_backtest as bt
R=Path('reports/ohio-pool-ranking-20261119')
def task(args):
 segment,row=args;d=R/segment;old=json.load(open(d/(row['ticker']+'-'+row['venue']+'-buy-baseline.json')));c=old['config'];c.update(quote_only=True,hy_fixed_quantity=row['fixed_baseline_tokens']);events=list(map(json.loads,open(d/(row['symbol']+'-bounded-events.jsonl'))));bbos=list(map(json.loads,open(d/(row['ticker']+'-'+row['venue']+'-bbo.jsonl'))));quotes=[]
 def observe(ns,q,v):quotes.append([ns,str(q),v.get('bid_usdg'),v.get('ask_usdg'),v['status'],v.get('reason')])
 result=bt.run(c,c['routes'][0],events,bbos,pool_observer=observe)
 (d/(row['ticker']+'-pool-quotes.json')).write_text(json.dumps(quotes));(d/(row['ticker']+'-quote-clock-audit.json')).write_text(json.dumps(dict(clock='Ohio state-update arrival and independent expiry timer; not gated on reference BBO',fixed_quantity=c['hy_fixed_quantity'],observations=len(quotes),**result),indent=2));print(segment,row['ticker'],len(quotes),result['truth_valid'],result['decision_valid'],flush=True)
if __name__=='__main__':
 rows=json.load(open(R/'selected-pools-with-baseline.json'))
 with concurrent.futures.ProcessPoolExecutor(max_workers=2) as ex:list(ex.map(task,[(s,r) for r in rows for s in ('train','test')]))
