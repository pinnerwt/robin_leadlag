"""Pool-keyed chronological validation, without choosing policies from test PnL."""
import json,math,datetime
from pathlib import Path
from decimal import Decimal as D
import numpy as np
from ohio_spot_hy import clean,scan
R=Path('reports/ohio-pool-ranking-20261119')
def metrics(x):
 closed=sum((D(c['excess_vs_episode_hold_usdg']) for c in x.get('cycles',[])),D(0));fills=len(x['fills']);reject=len(x['rejections'])
 return dict(side=x['entry_side'],open_bps=x['open_bps'],close_bps=x['close_bps'],fills=fills,cycles=len(x.get('cycles',[])),closed_excess_usdg=float(closed),marked_excess_usdg=float(D(x['excess_vs_hold_usdg'])),open_episode=x.get('open_episode_at_end'),pending=x['pending_at_end'],rejections=reject,break_even_cost_per_attempt=float(closed/(fills+reject)) if fills+reject else None,closed_less_001_per_attempt=float(closed-D('.01')*(fills+reject)),closed_less_005_per_attempt=float(closed-D('.05')*(fills+reject)))
def hy(segment,row):
 d=R/segment;quotes=json.load(open(d/(row['ticker']+'-pool-quotes.json')));bbos=list(map(json.loads,open(d/(row['ticker']+'-'+row['venue']+'-bbo.jsonl'))));seg=next(s for s in json.load(open(R/'segments.json')) if Path(s['directory']).name==segment);start=seg['start_utc_ns'];duration=(seg['end_utc_ns']-start)/1e6
 x,xb=clean(np.array([((seg['origin_ns']+r['mono_ns']-start)/1e6,(float(r['bid'])+float(r['ask']))/2) for r in bbos]));out={}
 for name,idx in [('bid',2),('ask',3),('mid',None)]:
  x,xb=clean(np.array([((seg['origin_ns']+r['mono_ns']-start)/1e6,(float(r['bid'])+float(r['ask']))/2 if name=='mid' else float(r[name])) for r in bbos]))
  points=[]
  for r in quotes:
   price=float('nan') if r[4]!='priced' else ((float(r[2])+float(r[3]))/2/float(r[1]) if idx is None else float(r[idx])/float(r[1]))
   points.append(((r[0]-start)/1e6,price))
  if len(points)<10:out[name]={'status':'insufficient_quotes'};continue
  y,yb=clean(np.array(points));full=scan(x,xb,y,yb,0,duration,step=2,limit=500,min_lag=1);full.pop('curve',None);folds=[scan(x,xb,y,yb,l,h,step=2,limit=500,min_lag=1) for l,h in zip(np.linspace(0,duration,4)[:-1],np.linspace(0,duration,4)[1:])]
  for f in folds:f.pop('curve',None)
  out[name]=dict(full=full,folds=folds,valid_quotes=sum(math.isfinite(p[1]) for p in points),invalid_quotes=sum(not math.isfinite(p[1]) for p in points))
 return out
def edge_diagnostics(segment,row):
 d=R/segment;quotes=json.load(open(d/(row['ticker']+'-pool-quotes.json')));bbos=list(map(json.loads,open(d/(row['ticker']+'-'+row['venue']+'-bbo.jsonl'))));seg=next(s for s in json.load(open(R/'segments.json')) if Path(s['directory']).name==segment)
 if not quotes or not bbos:return {'status':'no_quotes'}
 qt=np.array([r[0] for r in quotes],dtype=np.int64);times=np.array([seg['origin_ns']+r['mono_ns'] for r in bbos],dtype=np.int64);indices=np.searchsorted(qt,times,side='right')-1;safe=np.maximum(indices,0);valid=(indices>=0)&(times-qt[safe]<=1_000_000_000)
 bids=np.array([float(r[2])/float(r[1]) if r[4]=='priced' else np.nan for r in quotes]);asks=np.array([float(r[3])/float(r[1]) if r[4]=='priced' else np.nan for r in quotes]);out={}
 for side,values in [('buy',(np.array([float(r['bid']) for r in bbos])/asks[safe]-1)*10000),('sell',(bids[safe]/np.array([float(r['ask']) for r in bbos])-1)*10000)]:
  v=values[valid&np.isfinite(values)];out[side]={'observations':len(v),'p99_bps':float(np.quantile(v,.99)) if len(v) else None,'max_bps':float(np.max(v)) if len(v) else None,'observations_above_10bps':int(np.sum(v>=10))}
 return out
selected=json.load(open(R/'selected-pools-with-baseline.json'));allrows=[];summary=[]
for row in selected:
 per={};quality={}
 for segment in ['train','test']:
  result=[];q=[]
  for side in ['buy','sell']:
   path=R/segment/(row['ticker']+'-'+row['venue']+'-'+side+'-baseline.json');d=json.load(open(path));run=d.get('run',{});q.append(dict(side=side,error=d.get('error'),truth_valid=run.get('truth_valid'),decision_valid=run.get('decision_valid'),statistics=run.get('statistics'),quote_errors=run.get('decision_quote_errors')))
   for x in run.get('results',[]):
    m=metrics(x);err=run.get('statistics',{}).get('max_observed_price_error_bps',0);closed_turnover=sum(float(z['open']['amount_usdg'])+float(z['close_amount_usdg']) for z in x.get('cycles',[]));m['observed_swap_error_bps']=err;m['closed_turnover_usdg']=closed_turnover;m['closed_after_adverse_error_stress_usdg']=m['closed_excess_usdg']-closed_turnover*err/10000;result.append(m);allrows.append(dict(pool=row['pool'],ticker=row['ticker'],venue=row['venue'],segment=segment,**m))
  per[segment]=result;quality[segment]=q
 candidates=[r for r in per['train'] if r['cycles']>0 and r['closed_excess_usdg']>0]
 best=max(candidates,key=lambda r:(r['closed_excess_usdg'],r['cycles'],-r['rejections'])) if candidates else None
 test=next((r for r in per['test'] if all(r[k]==best[k] for k in ['side','open_bps','close_bps'])),None) if best else None
 # This fixed row remains descriptive if training found no positive closed cycles.
 fixed=[r for r in per['test'] if r['open_bps']=='10' and r['close_bps']=='-5']
 summary.append(dict(pool=row['pool'],ticker=row['ticker'],venue=row['venue'],fixed_baseline_tokens=row['fixed_baseline_tokens'],source_hy_training=row['full'],pool_hy_training=hy('train',row),pool_hy_test=hy('test',row),chosen_on_training=best,test_of_chosen=test,fixed_test_10_minus5=fixed,quality=quality,test_edge_diagnostics=edge_diagnostics('test',row)))
(R/'summary.json').write_text(json.dumps(summary,indent=2));(R/'all-scenarios.json').write_text(json.dumps(allrows,indent=2))
lines=['# Pool delay and fixed-baseline research','', 'Two disjoint one-hour Ohio windows; 20 ms execution assumption; about 500 USDG fixed token baseline + 500 USDG cash per isolated ticker scenario. Position cap is 500 USDG above baseline, sell floor zero. No cross-pool or portfolio profits are summed.','', 'Quotes include pool fees and size impact. Results exclude gas, failed-transaction costs, borrow/funding and issuer/FX basis. End marks are not liquidation proceeds. The initial equal exchange short is static and cancels in excess-versus-hold only under the stated equal-unit/FX assumptions.','', '| Pool ticker / source | Source lag train ms | Pool mid lag train / test ms | Chosen training side, open/close | Train closed USDG | Test closed USDG / cycles | Test marked USDG |','|---|---:|---|---|---:|---|---:|']
for r in summary:
 b=r['chosen_on_training'];t=r['test_of_chosen'];lag=lambda k:r[k].get('mid',{}).get('full',{}).get('peak_ms')
 lines.append(f"| {r['ticker']} / {r['venue']} | {r['source_hy_training']['peak_ms']} | {lag('pool_hy_training')} / {lag('pool_hy_test')} | {str((b['side'],b['open_bps'],b['close_bps'])) if b else 'No positive closed-cycle training policy'} | {b['closed_excess_usdg'] if b else '—'} | {str((t['closed_excess_usdg'],t['cycles'])) if t else '—'} | {t['marked_excess_usdg'] if t else '—'} |")
lines+=['','## Fixed 10 / -5 bps test rows (not selected by test returns)','', '| Ticker | Side | Fills | Closed cycles | Closed excess USDG | Marked excess USDG | Unclosed episode | Rejections |','|---|---|---:|---:|---:|---:|---|---:|']
for r in summary:
 for x in r['fixed_test_10_minus5']:lines.append(f"| {r['ticker']} | {x['side']} | {x['fills']} | {x['cycles']} | {x['closed_excess_usdg']:.6f} | {x['marked_excess_usdg']:.6f} | {x['open_episode']} | {x['rejections']} |")
lines+=['','## Executable-size HY by side','', 'Positive means the corresponding exchange BBO side leads the pool side. Fixed-size pool observations use state-update receipt times and independent expiry timers, without BBO freshness gating.','', '| Ticker / source | Train bid / ask lag ms | Later-hour bid / ask lag ms |','|---|---|---|']
for r in summary:
 def sides(k):return ' / '.join(str(r[k].get(side,{}).get('full',{}).get('peak_ms')) for side in ('bid','ask'))
 lines.append(f"| {r['ticker']} / {r['venue']} | {sides('pool_hy_training')} | {sides('pool_hy_test')} |")
lines+=['','## Positive closed-cycle test rows — exploratory, not training-selected','', '| Ticker | Side | Open / close bps | Cycles | Gross closed USDG | Worst observed swap error bps | Closed USDG after adverse-error stress |','|---|---|---|---:|---:|---:|---:|']
for x in allrows:
 if x['segment']=='test' and x['closed_excess_usdg']>0:lines.append(f"| {x['ticker']} | {x['side']} | {x['open_bps']} / {x['close_bps']} | {x['cycles']} | {x['closed_excess_usdg']:.6f} | {x['observed_swap_error_bps']:.3f} | {x['closed_after_adverse_error_stress_usdg']:.6f} |")
lines+=['', 'Adverse-error stress charges the worst observed validation discrepancy on each completed-cycle leg. This is an illustrative sensitivity, not a statistical error bound or a measured trading cost. No training policy had positive closed-cycle evidence unless explicitly shown above.']
lines+=['','## Interpretation','', 'Positive HY lag means venue leads the quoted pool; negative means pool leads. Source-mid screening is distinct from executable-size pool bid/ask HY. The scan is 0 and ±1,3,...499,500 ms. Boundary peaks and unstable chronological folds are not precise delay estimates.','', 'Only one checkpointed pool per ticker is present. The staged B89 WETH pool is excluded until the next recorder session, as requested. This run cannot establish the best pool for the same ticker. Offline route-selection tests enforce a shared ticker baseline/cap across hypothetical routes; they are not a measured cross-pool PnL backtest.','', 'Price-taker replay does not persist simulated fills into later historical liquidity. Calldata oracle acceptance is optimistic; pool depth reconciles from pushed logs. Check per-pool observed swap mismatch/errors in summary.json before trusting small edges. Chronological selection is confined to training. Preliminary shortened-window runs were already inspected before fixing kind-9 decoding; this is not a pristine never-seen holdout.','', 'Nitro kind 9 is decoded as retryable submission, not assumed executed calldata. All 23 submission hashes matched recorded logs; both full windows have zero extraction failures. Full retryable redemption execution is outside this decoder patch; missing tracked-pool execution metadata still fails replay extraction.']
(R/'RESULTS.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[:20]))
