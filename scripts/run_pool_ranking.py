"""Offline, pool-keyed fixed-baseline grid with disjoint chronological windows."""
import json,concurrent.futures,copy,time
from pathlib import Path
from decimal import Decimal as D,ROUND_FLOOR
import causal_spcx_backtest as bt
R=Path('reports/ohio-pool-ranking-20261119')
def task(args):
 segment,row,side,baseline=args;d=Path(segment['directory']);tag=row['ticker']+'-'+row['venue']+'-'+side;path=d/(tag+'-baseline.json')
 if path.exists():return
 c=json.load(open('config/spcx-ohio-translated-backtest.json'))
 for k in ('initial_mark_price_usdg','initial_position_tokens'):c.pop(k,None)
 c.update(checkpoint=str(d/(row['symbol']+'-seed.json')),symbol=row['symbol'],provider_mode='provider-full',fixed_baseline=True,hy_fixed_quantity=baseline,initial_position_tokens=baseline,initial_inventory_usdg='0',initial_cash_usdg='500',entry_side=side,warmup_seconds=segment['ready_ns']/1e9,return_invalid_diagnostics=True,cache_no_order=True,diagnostic_probes=False,share_candidate_evaluations=True,open_close_grid=[dict(open_bps=str(o),close_bps=str(cl)) for o in (10,15,20,25,30) for cl in (-10,-5,0,5)])
 c['routes']=[dict(name='ohio_receipt_exec20',chain_shift_ms=0,truth_chain_shift_ms=0,binance_shift_ms=0,execution_ms=20)];c['route_assumptions']='Actual Ohio receipt timestamps; 20 ms fixed fill delay, no additional Taiwan translation.';c['initial_inventory_assumption']='Same fixed token baseline across train/test and buy/sell, valued near 500 USDG at first training BBO; 500 USDG cash. Independent reset at each checkpoint window, not continuous portfolio.'
 es=list(map(json.loads,open(d/(row['symbol']+'-bounded-events.jsonl'))));bs=list(map(json.loads,open(d/(row['ticker']+'-'+row['venue']+'-bbo.jsonl'))));series=[]
 def observe(ns,q,v):series.append([ns,str(q),v.get('bid_usdg'),v.get('ask_usdg'),v['status'],v.get('reason')])
 out=dict(pool=row['pool'],ticker=row['ticker'],venue=row['venue'],segment=d.name,config=c,scope='conditional price-taker, provider-full local EVM, assumed-success auxiliary calldata; no persistent own-fill impact; USD/USDG/USDT parity; gross of gas and hedge carry')
 print('start',d.name,tag,len(es),len(bs),flush=True)
 try:out['run']=bt.run(c,c['routes'][0],es,bs,pool_observer=observe if side=='buy' else None)
 except Exception as exc:out['error']=repr(exc)
 path.write_text(json.dumps(out,indent=2)+'\n')
 if side=='buy':(d/(row['ticker']+'-pool-quotes.json')).write_text(json.dumps(series))
 r=out.get('run',{});print('done',d.name,tag,'valid',r.get('truth_valid'),r.get('decision_valid'),'max_cycles',max([len(x.get('cycles',[])) for x in r.get('results',[])],default=0),out.get('error'),flush=True)
if __name__=='__main__':
 selected=json.load(open(R/'selected-pools.json'));segments=json.load(open(R/'segments.json'));tasks=[]
 for row in selected:
  first=json.loads(next(open(R/'train'/(row['ticker']+'-'+row['venue']+'-bbo.jsonl'))));baseline=str((D(500)/D(first['ask'])).quantize(D('1e-18'),rounding=ROUND_FLOOR));row['fixed_baseline_tokens']=baseline
  for segment in segments:
   for side in ('buy','sell'):tasks.append((segment,row,side,baseline))
 (R/'selected-pools-with-baseline.json').write_text(json.dumps(selected,indent=2))
 with concurrent.futures.ProcessPoolExecutor(max_workers=2) as ex:list(ex.map(task,tasks))
