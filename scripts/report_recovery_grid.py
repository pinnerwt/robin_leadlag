"""Summarize isolated checkpoint episodes, separating state-quality classes."""
import json,collections,argparse
from pathlib import Path
from decimal import Decimal as D
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--full',action='store_true');p.add_argument('--entry-side',choices=['buy','sell'],default='sell');a=p.parse_args();rows={};coverage=collections.defaultdict(lambda:collections.defaultdict(lambda:dict(segments=0,hours=0,swaps=0,max_error_bps=0)));errors=[]
for path in sorted(a.directory.glob('segment-*/*-grid.json')):
 if path.name.endswith('-full-grid.json')!=a.full:continue
 if ('-buy-'in path.name)!=(a.entry_side=='buy'):continue
 out=json.load(open(path));sym=out['symbol'];status=out['status'];
 if a.full and status=='conditional_small_error'and out.get('run',{}).get('decision_quote_errors'):status='provider_rejections'
 c=coverage[sym][status];c['segments']+=1;c['hours']+=max(0,out['end_ns']-out['start_ns'])/3.6e12
 if 'run'not in out:errors.append(dict(path=str(path),status=status,error=out.get('error')));continue
 r=out['run'];c['swaps']+=r['statistics'].get('observed_swap_count',0);c['max_error_bps']=max(c['max_error_bps'],r['statistics'].get('max_observed_price_error_bps',0))
 for x in r['results']:
  k=(sym,status,int(x['execution_ms']),x['open_bps'],x['close_bps'])
  if k not in rows:rows[k]=dict(symbol=sym,status=status,latency_ms=k[2],open_bps=k[3],close_bps=k[4],segments=0,buys=0,sells=0,flips=0,cycles=0,rejected=0,pending_at_end=0,open_episodes_at_end=0,excess_vs_hold_usdg=D(0),marked_pnl_usdg=D(0),realized_pnl_usdg=D(0),hold_pnl_usdg=D(0),cycle_excess_usdg=D(0))
  v=rows[k];v['segments']+=1
  for f in ('buys','sells','flips'):v[f]+=x[f]
  v['cycles']+=x['completed_cycles'];v['rejected']+=sum(x['cancelled'].values());v['pending_at_end']+=x['pending_at_end'];v['open_episodes_at_end']+=x['open_episode_at_end']
  for dest,source in [('excess_vs_hold_usdg','excess_vs_hold_usdg'),('marked_pnl_usdg','binance_mark_pnl_usdg'),('realized_pnl_usdg','realized_pnl_usdg'),('hold_pnl_usdg','hold_pnl_usdg')]:v[dest]+=D(x[source])
  v['cycle_excess_usdg']+=sum((D(cy['excess_vs_episode_hold_usdg'])for cy in x['cycles']),D(0))
serial=[{k:str(v)if isinstance(v,D)else v for k,v in r.items()}for r in rows.values()]
(a.directory/(('summary-buy-full.json' if a.full else 'summary-buy.json') if a.entry_side=='buy' else ('summary-full.json' if a.full else 'summary.json'))).write_text(json.dumps(dict(coverage=coverage,rows=serial,errors=errors),indent=2)+'\n')
lines=['# 200–260 ms open/close sweep'+(' — full provider' if a.full else ' — source-only approximation'),'', 'Offline, sell-first single-leg model. Each checkpoint segment independently starts with 500 USDG worth of base inventory and zero cash. No hedge and no fixed holding time. Open sells, close buys back. 1 bps submitted slippage limit; original size is repriced at execution. Fees and size impact are in the local pool quote. USDG/USDT=1; gas/revert cost zero. Own fills do not change later historical liquidity.','', 'Latency is total effective delay on the Taiwan receipt timeline, with no extra feed shifts. It is not an independently measured Ohio route model. Source guards/expiry remain approximate; pinned source/provider ratios are recalibrated at each checkpoint only. Segments stop before undecoded Nitro or unmatched pool transactions. A new checkpoint resets the portfolio, so sums below are episode aggregates, not continuous-account returns.','', 'Best rows are selected in-sample from 40 threshold pairs at each latency. They are exploratory, not an independently validated policy. Marked open inventory uses Binance; it is not a guaranteed pool liquidation value.','', '## Coverage','', '| Token | Quality | Segments | Hours | Observed swaps | Max quote error bps |','|---|---|---:|---:|---:|---:|']
for sym,ss in sorted(coverage.items()):
 for status,c in ss.items():lines.append(f"| {sym} | {status} | {c['segments']} | {c['hours']:.3f} | {c['swaps']} | {c['max_error_bps']:.4f} |")
lines+=['','`conditional_small_error` requires both state views to survive and max observed swap quote error <=1 bps. This is a conditional model result, not a proof of executable parity at every update. State-failed outputs are excluded from the rankings.','', '## Best conditional rows per token and latency','', '| Token | Delay ms | Open / close bps | Excess vs hold USDG | Marked PnL USDG | Cycles | Sells / buys | Rejections |','|---|---:|---|---:|---:|---:|---|---:|']
for sym in sorted(coverage):
 for ms in range(200,261,10):
  candidates=[r for r in rows.values()if r['symbol']==sym and r['status']=='conditional_small_error'and r['latency_ms']==ms]
  if not candidates:continue
  r=max(candidates,key=lambda r:(r['excess_vs_hold_usdg'],-r['rejected'],-D(r['open_bps'])))
  lines.append(f"| {sym} | {ms} | {r['open_bps']} / {r['close_bps']} | {r['excess_vs_hold_usdg']:+.6f} | {r['marked_pnl_usdg']:+.6f} | {r['cycles']} | {r['sells']} / {r['buys']} | {r['rejected']} |")
lines+=['','## Full grid','', '| Token | Quality | Delay | Open | Close | Excess vs hold USDG | Cycles | Sells | Buys |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
for r in sorted(rows.values(),key=lambda r:(r['symbol'],r['status'],r['latency_ms'],D(r['open_bps']),D(r['close_bps']))):
 lines.append(f"| {r['symbol']} | {r['status']} | {r['latency_ms']} | {r['open_bps']} | {r['close_bps']} | {r['excess_vs_hold_usdg']:+.6f} | {r['cycles']} | {r['sells']} | {r['buys']} |")
if a.entry_side=='buy':
 lines=[line.replace('sell-first single-leg','buy-first single-leg').replace('500 USDG worth of base inventory and zero cash','500 USDG cash and zero base inventory').replace('Open sells, close buys back','Open buys, close sells').replace('holding those same initial tokens','holding the initial cash') for line in lines]
if a.full:
 lines.insert(2,'Full-provider mode produced no fills. Provider rejections/state failures prevent interpreting this as evidence of no market opportunity. Full provider guards are executed here, but their evolving dependencies are not proven complete.')
else:
 lines.insert(2,'WARNING: These are source-only model outputs. The full-provider rerun produced no fills and provider rejections/state failures. Positive values below are NOT validated executable returns; see CONCLUSIONS.md.')
(a.directory/(('RESULTS-buy-full.md' if a.full else 'RESULTS-buy.md') if a.entry_side=='buy' else ('RESULTS-full.md' if a.full else 'RESULTS.md'))).write_text('\n'.join(lines)+'\n');print('pool-segment files',sum(c['segments']for s in coverage.values()for c in s.values()),'aggregate rows',len(rows))
