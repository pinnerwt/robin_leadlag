"""Separate usable replay results from gaps and model errors on the new tape."""
import argparse,json,datetime
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',required=True);a=p.parse_args();B=Path(a.base);O=B/'open-close';rows=[];quality=[]
for m in json.load(open(B/'manifest.json')):
 s=m['symbol'];d=json.load(open(O/(s+'-backtest.json')));audit=json.load(open(B/(s+'-calibrated-audit.json')))
 if 'run'not in d:quality.append(dict(symbol=s,status='failed',reason=d['error']));continue
 r=d['run'];error=max(audit['max_price_error_bps'],r['statistics'].get('max_observed_price_error_bps',0));valid=r['truth_valid']and r['decision_valid']and not audit['errors'];grade='state_failed' if not valid else ('small_observed_quote_error' if error<0.01 else 'approximate_only')
 quality.append(dict(symbol=s,status=grade,max_observed_price_error_bps=error,swap_count=audit['counts'].get('swaps',0),statistics=r['statistics'],audit_errors=audit['errors']))
 for x in r['results']:
  rows.append(dict(symbol=s,status=grade,open_bps=x['open_bps'],close_bps=x['close_bps'],buys=x['buys'],sells=x['sells'],cycles=x['completed_cycles'],flips=x['flips'],pnl=float(x['binance_mark_pnl_usdg']),hold=float(x['hold_pnl_usdg']),excess=float(x['excess_vs_hold_usdg']),turnover=float(x['turnover_usdg']),open_episode=x['open_episode_at_end']))
assert len(rows)==440 and len(quality)==11
snapshot=json.load(open(B/'snapshot.json'));coverage=json.load(open(B/'coverage-summary.json'));window=json.load(open(B/'analysis-window.json'));recovery=json.load(open(B/'recovery-checkpoint.json'))
summary=dict(coverage=coverage,window=window,recovery=recovery,quality=quality,rows=rows)
(B/'RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n')
lines=['# New-capture all-ticker backtest','',
'All 11 tickers and the 40 previously frozen open/close combinations were evaluated: 440 scenario results. The usable raw interval is 2026-11-16 09:08:24–12:38:18 UTC (Taiwan 17:08–20:38), with a 120-second initial warmup. This is a new recording, separate from the earlier two-hour development tape.',
'', '**The full approximately 13h50m recorded prefix cannot be treated as a continuous pool-state replay.** Its first chain WebSocket gap occurs at 12:38:23 UTC; the analysis ends five seconds earlier. The captured prefix contains 26 chain gaps, 140 Nitro gaps and one Binance-connection gap. Binance had three redundant streams; a gap on one connection is not automatically a loss of market data. No fresh checkpoint was taken on reconnect by the running recorder. Reconnecting transport does not prove missing pool updates were restored.',
'', 'The recorder was not stopped or restarted. The compressed stream is still open; a fixed compressed-byte prefix was scanned for coverage, and only complete binary records were interpreted. The expected zstd premature-end diagnostic at the live tail is not the reason for excluding the later hours. State continuity gaps are the reason.',
'', '## Comparable fixed policy: open 5 / close −5 bps','',
'Each pool independently starts with approximately 500 USDG of base tokens and zero cash. Open sells inventory; close buys back affordable exposure up to the 500 USDG cap. Both Taiwan feed clocks are translated to hypothetical Ohio receipt times (Binance +100 ms; chain −175 ms), followed by 20 ms order arrival and immediate execution assumed. Pool fees and per-fill size impact are included; gas and revert costs are zero. Orders use 1 bps fixed slippage limits.',
'', '| Ticker | Sells / buys | Cycles | Marked PnL USDG | Excess vs hold USDG | Price error bps | Status |','|---|---:|---:|---:|---:|---:|---|']
for q in quality:
 r=next(x for x in rows if x['symbol']==q['symbol']and x['open_bps']=='5'and x['close_bps']=='-5')
 lines.append(f"| {q['symbol']} | {r['sells']} / {r['buys']} | {r['cycles']} | {r['pnl']:+.6f} | {r['excess']:+.6f} | {q['max_observed_price_error_bps']:.6f} | {q['status']} |")
lines+=['','Only SPCX, META, TSLA, GOOGL, AAPL and QQQ have complete state replay and small observed quote errors in this sample. All 40 policies have zero fills for each of these six pools. Their negative marked PnL is initial-inventory depreciation, not losses from executed strategy trades. Their strategy excess versus holding is zero. This is a sell-first strategy, so no fills does not establish that a cash-funded buy-first strategy has no opportunities.',
'', 'MU has one simulated cycle under 5/−5, but its approximately 5.04 bps quote error is material to that threshold. SPY has one simulated sale under 5/−5 with approximately 4.00 bps error. NVDA and INTC errors are approximately 8.00 and 7.65 bps. ETH state replay fails. Those five tickers are diagnostic results, not validated tradable returns. ETH numbers after failure are especially not meaningful strategy evaluations.',
'', '## Recovery attempt','', recovery['reason'],
'', 'The original capture and its initial sparse checkpoint are preserved. No historical gaps were silently repaired, and no recovery snapshot is claimed. A usable new pinned checkpoint is required before a later continuous segment can be trusted.',
'', '## Full frozen grid','', '| Ticker | Open bps | Close bps | Cycles | Flips | Marked PnL USDG | Excess vs hold USDG | Status |','|---|---:|---:|---:|---:|---:|---:|---|']
for r in rows:lines.append(f"| {r['symbol']} | {r['open_bps']} | {r['close_bps']} | {r['cycles']} | {r['flips']} | {r['pnl']:+.6f} | {r['excess']:+.6f} | {r['status']} |")
lines+=['','Model limitations: startup-only source calibration, incomplete provider guards/fallbacks, hypothetical constant network offsets, no extra sequencing queue, and own fills not persisted into later historical state. Small observed swap errors are not a guarantee for every hypothetical quote; successful-swap samples for SPCX and TSLA are only two and one, respectively.','', 'The old grid was preserved exactly rather than tuned to this new sample. Choosing a winning row from the new grid would still be selection on this sample. Receiver/sender identity is not needed for this configured price-only decoder: sender recovery was omitted offline, and a 100-transaction parity check confirmed hashes, calldata and all other decoded fields match the original decoder.','', 'Artifacts: `snapshot.json`, `gaps.jsonl`, `coverage-summary.json`, `analysis-window.json`, `RESULTS.json`, per-pool audits and `open-close/*-backtest.json`.']
(B/'RESULTS.md').write_text('\n'.join(lines)+'\n')
print('Reported',len(rows),'scenarios; high-fidelity pools',sum(q['status']=='small_observed_quote_error'for q in quality))
