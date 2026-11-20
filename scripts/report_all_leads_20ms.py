"""Report every positive full-sample X -> Robinhood source HY candidate."""
import json,statistics
from pathlib import Path
B=Path('reports/ohio-20ms-backtest')
selection=json.loads((B/'all-leads-selection.json').read_text());summary=[];overview=[];ages=[]
lines=['# All positive HY leads: Ohio 20 ms backtest','',
'2026-11-19 03:33:01–04:03:01 UTC recording window. Actual Ohio ingress timestamps; no geographic latency adjustment. ETH has approximately 27.8 minutes of overlapping data. BBO tapes end slightly before the requested cutoff.',
'', 'Selection: every mid-price HY row with X = a spot exchange, Y = robinhood_source, full-sample peak > 0 ms. Includes unstable candidates without a fold filter. Six tickers, eight source/pool combinations. Positive full-sample HY is not proof of statistical significance or trading profitability.',
'', 'Configuration: 500 USDG per-token maximum; buy-first starts with 500 USDG cash; sell-first starts with 500 USDG of tokens at the first source ask. Open 10/15/20/25/30 bps, close -10/-5/0/5 bps, both directions, 20 ms execution delay, no fixed hold and no hedge. All 320 scenarios are independent, not a shared portfolio.',
'', 'Buy trigger compares source bid to size-specific pool ask cost; sell trigger compares size-specific pool bid proceeds to source ask. Full local provider checks at signal and execution, fees and immediate size impact included. A negative close edge permits that disadvantage against the source. Submitted limits allow 1 bp, source BBO freshness limit 1 s.',
'', '## HY selection and state fidelity','',
'Fold counts below are descriptive; the same recording is used for selection and backtesting. A +100 ms boundary peak means the best lag may be outside the scanned range.',
'', '| Source | HY peak ms | Positive 10-fold partitions | Peak with 5 s gap limit | Historical swaps | Token-delta mismatches | Max price error bps |','|---|---:|---:|---:|---:|---:|---:|']
for m in selection:
 audit=json.loads((B/(m['symbol']+'-aux-audit.json')).read_text());assert not audit['errors']
 lines.append(f"| {m['ticker']} / {m['venue']} | +{m['peak_ms']}{'*' if m['boundary'] else ''} | {m['positive_folds']}/{m['valid_folds']} | {m['gap5s_peak_ms']} | {audit['counts']['swaps']} | {audit['counts']['mismatch']} | {audit['max_price_error_bps']:.6f} |")
 for side in ['buy','sell']:
  path=B/(m['ticker']+'-'+m['venue']+'-'+side+'.json');root=json.loads(path.read_text());r=root['run'];assert r['truth_valid'] and r['decision_valid'];assert len(r['results'])==20
  for s in r['results']:
   for f in s['fills']:assert f['fill_ns']-f['signal_ns']==20_000_000
   row=dict(ticker=m['ticker'],venue=m['venue'],entry_side=side,open_bps=s['open_bps'],close_bps=s['close_bps'],fills=len(s['fills']),buys=sum(f['side']=='buy' for f in s['fills']),sells=sum(f['side']=='sell' for f in s['fills']),cycles=len(s['cycles']),closed_cycle_excess_usdg=sum(float(c['excess_vs_episode_hold_usdg']) for c in s['cycles']),accounting_realized_usdg=float(s['realized_pnl_usdg']),marked_excess_vs_initial_hold_usdg=float(s['excess_vs_hold_usdg']),episode_open_at_end=s['open_episode_at_end'],final_base=s['base_tokens'],final_cash=s['cash_usdg'],cancelled=s['cancelled'],hy_peak_ms=m['peak_ms'],positive_folds=m['positive_folds'],swap_max_error_bps=audit['max_price_error_bps'],results_file=str(path))
   summary.append(row)
   if s['open_bps']=='10' and s['close_bps']=='-10':overview.append(row)
  fs={(f['signal_ns'],f['side'],f['size_tokens']):f for s in r['results'] for f in s['fills']}
  age=dict(ticker=m['ticker'],venue=m['venue'],entry_side=side,unique_simulated_fills=len(fs),decision_quote_errors=r['decision_quote_errors'],execution_quote_errors=r['execution_quote_errors'])
  for key in ['signal_source_age_ms','execution_source_age_ms','provider_block_source_age_ms','signal_aux_age_ms','execution_aux_age_ms','provider_block_aux_age_ms']:
   values=[f[key] for f in fs.values()];age[key]=dict(min=min(values),median=statistics.median(values),max=max(values)) if values else None
  ages.append(age)
lines+=['','## Fixed comparison: open 10 / close -10 bps','',
'Closed-cycle excess uses each completed episode versus holding its start portfolio. Final marked excess uses the initial portfolio hold benchmark and includes open inventory (or foregone appreciation after selling). They use different horizons and must not be added together. Remaining inventory is marked at source bid, not liquidated against the pool.',
'', '| Source | First side | Buys / sells | Completed cycles | Closed-cycle excess USDG | Final marked excess USDG | Episode open |','|---|---|---:|---:|---:|---:|:---:|']
for r in overview:lines.append(f"| {r['ticker']} / {r['venue']} | {r['entry_side']} | {r['buys']} / {r['sells']} | {r['cycles']} | {r['closed_cycle_excess_usdg']:.6f} | {r['marked_excess_vs_initial_hold_usdg']:.6f} | {r['episode_open_at_end']} |")
lines+=['','## Provider age at simulated executions','',
'Ranges deduplicate identical fills across threshold scenarios. Wall-clock age and block timestamp age are distinct. No expiry cutoff is bypassed; a quote rejection is not counted as a fill.',
'', '| Source / first side | Source wall age range ms | Auxiliary wall age range ms | Source contract age range ms | Quote errors (decision / execution) |','|---|---:|---:|---:|---:|']
for a in ages:
 if not a['unique_simulated_fills']:continue
 def interval(k):
  v=a[k];return f"{v['min']:.3f}–{v['max']:.3f}"
 lines.append(f"| {a['ticker']} / {a['venue']} / {a['entry_side']} | {interval('execution_source_age_ms')} | {interval('execution_aux_age_ms')} | {interval('provider_block_source_age_ms')} | {sum(a['decision_quote_errors'].values())} / {sum(a['execution_quote_errors'].values())} |")
lines+=['','## Full threshold grid','',
'Accounting realized PnL for sell-first uses the initial bid mark as cost basis, not historical acquisition cost; a single inventory sale is not a completed trading cycle. The tables emphasize cycle excess and marked excess instead. Gas and revert costs are excluded.']
for m in selection:
 for side in ['buy','sell']:
  lines+=['',f"### {m['ticker']} / {m['venue']}: {side}-first",'', '| Open | Close | Fills | Cycles | Closed-cycle excess USDG | Final marked excess USDG | Open episode | Rejections |','|---:|---:|---:|---:|---:|---:|:---:|---:|']
  for r in summary:
   if (r['ticker'],r['venue'],r['entry_side'])!=(m['ticker'],m['venue'],side):continue
   lines.append(f"| {r['open_bps']} | {r['close_bps']} | {r['fills']} | {r['cycles']} | {r['closed_cycle_excess_usdg']:.6f} | {r['marked_excess_vs_initial_hold_usdg']:.6f} | {r['episode_open_at_end']} | {sum(r['cancelled'].values())} |")
lines+=['','## Scope and limitations','',
'Local state uses both compressed source and auxiliary oracle calldata; historical pool push logs reconcile depth. Auxiliary feed dependencies for the newly included pools were identified from local provider storage reads. All auxiliary feed advances in this tape were previously validated against pushed FeedUpdated IDs. No remote RPC is used for this replay.',
'', 'META is approximate: six of seven observed swaps differ in token deltas, maximum implied price error about 4 bps. ETH has a maximum error about 1 bp. Do not treat threshold distinctions within those errors as precise. AAPL, NVDA, QQQ and SPCX match observed swaps exactly, but AAPL has only five validation swaps.',
'', 'No persistent own-fill impact on subsequent historical depth, no full funding/allowance/router transaction simulation, no signature verification, no gas/revert costs or network jitter/queue competition. USDG/USD/USDT parity assumed. Tokenized instruments on different venues need not be economically identical or directly transferable. Apparent static price gaps and directional gains do not establish a latency advantage.',
'', 'This is an exploratory same-window test. HY candidate selection, threshold comparison and outcomes all reuse this short overnight tape. More independent data and out-of-sample evaluation are needed; no best-threshold profitability claim is made.',
'', 'Machine-readable artifacts: all-leads-summary.json (320 scenarios), all-leads-provider-ages.json, all-leads-selection.json, all-leads-bbo-quality.json. Original three-source report remains in RESULTS.md.']
assert len(summary)==320
(B/'all-leads-summary.json').write_text(json.dumps(summary,indent=2)+'\n');(B/'all-leads-provider-ages.json').write_text(json.dumps(ages,indent=2)+'\n');(B/'ALL_LEADS.md').write_text('\n'.join(lines)+'\n')
print('Reported',len(summary),'scenarios')
for r in overview:
 if r['fills']:print(r['ticker'],r['venue'],r['entry_side'],'buys/sells',r['buys'],r['sells'],'cycles',r['cycles'],'cycle_excess',round(r['closed_cycle_excess_usdg'],6),'marked',round(r['marked_excess_vs_initial_hold_usdg'],6))
