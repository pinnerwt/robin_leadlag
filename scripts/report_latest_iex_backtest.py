"""Summarize completed chronological IEX runs without selecting on later PnL."""
import json
from pathlib import Path
from decimal import Decimal as D
R=Path('reports/ohio-latest-20261119T2103Z')
def metrics(x,run):
 closed=sum((D(c['excess_vs_episode_hold_usdg'])for c in x.get('cycles',[])),D(0));turnover=sum(float(c['open']['amount_usdg'])+float(c['close_amount_usdg'])for c in x.get('cycles',[]));err=run.get('statistics',{}).get('max_observed_price_error_bps',0)
 return dict(side=x['entry_side'],open_bps=x['open_bps'],close_bps=x['close_bps'],fills=len(x['fills']),cycles=len(x.get('cycles',[])),closed_usdg=float(closed),marked_usdg=float(x['excess_vs_hold_usdg']),open_episode=x.get('open_episode_at_end'),rejections=len(x['rejections']),cancelled=x['cancelled'],closed_turnover_usdg=turnover,closed_less_001_per_attempt=float(closed)-.01*(len(x['fills'])+len(x['rejections'])),closed_less_005_per_attempt=float(closed)-.05*(len(x['fills'])+len(x['rejections'])),max_swap_error_bps=err,closed_after_error_stress_usdg=float(closed)-turnover*err/10000,valid=run.get('truth_valid')and run.get('decision_valid'))
rows=[];summaries=[]
for m in json.load(open(R/'manifest.json')):
 if m['symbol']=='ETHUSDT':continue
 ticker=m['symbol'].removesuffix('BUSDT');per={};quality=[]
 for segment in ('train','test'):
  per[segment]=[]
  for side in ('buy','sell'):
   d=json.load(open(R/f'{ticker}-{segment}-{side}.json'));run=d.get('run',{});quality.append(dict(segment=segment,side=side,error=d.get('error'),truth_valid=run.get('truth_valid'),decision_valid=run.get('decision_valid'),statistics=run.get('statistics')))
   for x in run.get('results',[]):
    v=metrics(x,run);per[segment].append(v);rows.append(dict(ticker=ticker,pool=m['pool'],segment=segment,**v))
 eligible=[x for x in per['train']if x['valid']and x['cycles']>0 and x['closed_usdg']>0];chosen=max(eligible,key=lambda x:(x['closed_usdg'],x['cycles'],-x['rejections']))if eligible else None
 heldout=next((x for x in per['test']if all(x[k]==chosen[k]for k in ('side','open_bps','close_bps'))),None)if chosen else None
 summaries.append(dict(ticker=ticker,pool=m['pool'],chosen_training=chosen,test_selected=heldout,fixed_test=[x for x in per['test']if x['open_bps']=='10'and x['close_bps']=='-5'],quality=quality))
selected_trades=[]
for item in summaries:
 chosen=item['chosen_training']
 if chosen:
  run=json.load(open(R/f"{item['ticker']}-test-{chosen['side']}.json"))['run']
  scenario=next(x for x in run['results']if all(x[k]==chosen[k]for k in ('open_bps','close_bps')))
  selected_trades.append(dict(ticker=item['ticker'],pool=item['pool'],open_bps=chosen['open_bps'],close_bps=chosen['close_bps'],fills=scenario['fills'],cycles=scenario['cycles'],rejections=scenario['rejections']))
(R/'selected-trades.json').write_text(json.dumps(selected_trades,indent=2))
(R/'summary.json').write_text(json.dumps(summaries,indent=2));(R/'all-scenarios.json').write_text(json.dumps(rows,indent=2))
lines=['# Latest Ohio IEX → Metric backtest','','Train: 2026-11-19 14:30:00–14:57:31.734 UTC. Later test: 14:57:31.734–15:46:54.711 UTC. Latest source files downloaded through 21:01 UTC; later chain data is excluded because checkpoint coverage ended at the first head discontinuity and did not recover. No recorders restarted.','','Each ticker starts with fixed stock tokens worth about 500 USDG at the first training ask, plus 500 USDG cash; maximum extra inventory 500 USDG above baseline, selling limited to existing tokens. Train/test reset positions independently, retaining the same token baseline. Both sides and 20 thresholds per side run independently. Actual Ohio arrival clocks, fixed 20 ms execution delay, 1 bp submission slippage limit. IEX own-venue BBO is the signal.','','Open thresholds 10/15/20/25/30 bps; close thresholds -10/-5/0/5 bps. Close threshold applies to the opposite side versus contemporaneous IEX bid/ask, not a profit target or holding-time exit. Pool fees and size impact included; gas, failed transaction charges, borrow/carry and USDG/USD basis excluded. Closed USDG means excess versus holding baseline over completed cycles; marked excess includes open risk and is not liquidation PnL. Static exchange hedge is not simulated. Simulated fills do not persist their impact into future historical depth.','','| Ticker | Training-selected side/open/close | Train closed USDG | Later closed USDG | Later cycles | Later marked USDG | Open episode | Max swap error bps | Later closed after error stress USDG |','|---|---|---:|---:|---:|---:|---|---:|---:|']
for s in summaries:
 a=s['chosen_training'];b=s['test_selected']
 if not a:lines.append(f"| {s['ticker']} | No positive valid closed-cycle training policy | — | — | — | — | — | — | — |");continue
 lines.append(f"| {s['ticker']} | {a['side']} / {a['open_bps']} / {a['close_bps']} | {a['closed_usdg']:.4f} | {b['closed_usdg']:.4f} | {b['cycles']} | {b['marked_usdg']:.4f} | {b['open_episode']} | {b['max_swap_error_bps']:.4f} | {b['closed_after_error_stress_usdg']:.4f} |")
lines+=['','## Fixed 10/-5 bps later test — no selection on test returns','','| Ticker | Side | Closed USDG | Cycles | Marked USDG | Fills / rejects | Open episode | State valid |','|---|---|---:|---:|---:|---|---|---|']
for s in summaries:
 for x in s['fixed_test']:lines.append(f"| {s['ticker']} | {x['side']} | {x['closed_usdg']:.4f} | {x['cycles']} | {x['marked_usdg']:.4f} | {x['fills']} / {x['rejections']} | {x['open_episode']} | {x['valid']} |")
lines+=['','## Quality','','Any invalid-state run is excluded from policy selection and is not usable profit evidence. Full per-pool parity counts, errors and cancellations are in summary.json. Worst observed swap price discrepancy is also charged against completed-cycle turnover as an illustrative adverse-error sensitivity in all-scenarios.json, not a statistical bound. Threshold selection is chronological but the early window was previously inspected for HY, so this is exploratory research. There is only one stock pool per ticker in this comparison; ETH and other exchanges are outside this IEX-only run.','','See REPLAY_FIX.md for scoped local decoder changes and checksums.json under the capture directory for remote-prefix integrity.']
extra=[]
for segment in ('train','test'):
 d=json.load(open(R/f'SPY-{segment}-sell-wide-close.json'));run=d.get('run',{})
 for x in run.get('results',[]):extra.append(dict(segment=segment,**metrics(x,run)))
(R/'spy-wide-close-summary.json').write_text(json.dumps(extra,indent=2))
lines+=['','## Post-hoc SPY wider close thresholds','','Added after inspecting the later-window close-edge distribution: not independent validation. Same open=10 bps, sell-first, 20 ms delay. At every signal, buy edge = IEX bid / pool ask per token - 1; sell edge = pool bid per token / IEX ask - 1. Pool quotes include size impact and fees. Negative close edges allow paying a premium to restore baseline.','','| Window | Close bps | Closed USDG | Cycles | Marked USDG | Fills / rejects | Open episode |','|---|---:|---:|---:|---:|---|---|']
for x in extra:lines.append(f"| {x['segment']} | {x['close_bps']} | {x['closed_usdg']:.4f} | {x['cycles']} | {x['marked_usdg']:.4f} | {x['fills']} / {x['rejections']} | {x['open_episode']} |")
hy=json.load(open(R/'pool-hy-test.json'))
lines+=['','## Later-window fixed-size pool HY','','Positive means IEX leads the matching pool quote side. Scan ±500 ms at 2 ms spacing plus zero/endpoints; five chronological folds. Size is fixed near 500 USDG, separate from the backtest variable order size. Point estimates and search boundaries are not precise latency guarantees.','','| Ticker | Bid peak ms | Ask peak ms | Positive bid folds / 5 | Positive ask folds / 5 |','|---|---:|---:|---:|---:|']
for row in hy['results']:
 b=row['sides']['bid'];a=row['sides']['ask'];lines.append(f"| {row['ticker']} | {b['wide_all'].get('peak_ms')} | {a['wide_all'].get('peak_ms')} | {sum(f.get('peak_ms',0)>0 for f in b['wide_fold5'])} | {sum(f.get('peak_ms',0)>0 for f in a['wide_fold5'])} |")
lines+=['','SPCX shows fold sign reversals despite some profitable cycles. A profitable single-leg episode does not establish that timing advantage caused its profit. No annualization or stable-profit claim is made.']
(R/'RESULTS.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[:20]))
