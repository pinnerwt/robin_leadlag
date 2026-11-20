"""Report all episode grids; keep cycles, fills, and marked PnL distinct."""
import json,datetime
from pathlib import Path
B=Path('reports/metric-multi-latest/open-close');frozen=json.load(open(B/'frozen-grid.json'));rows=[];quality=[]
for symbol in frozen['symbols']:
 p=B/(symbol+'-backtest.json')
 if not p.exists():continue
 d=json.loads(p.read_text());c=d['config'];r=d['run'];seed=json.load(open(c['checkpoint']));word_id=seed['pools'][0]['word_id']
 c['binding_assumption']=f'Direct compressed word ID {word_id:#x} maps to {symbol} from pinned source-contract storage; no future acceptance filtering in signals.'
 c['threshold_mode']='episode: open sells initial token exposure; close buys maximum affordable exposure up to the position cap'
 c['initial_inventory_assumption']='Approximately 500 USDG of base tokens, zero cash. Close restores affordable base exposure up to the 500 USDG cap, not necessarily the original token quantity.'
 p.write_text(json.dumps(d,indent=2)+'\n');(B/(symbol+'-config.json')).write_text(json.dumps(c,indent=2)+'\n')
 quality.append(dict(symbol=symbol,truth_valid=r['truth_valid'],decision_valid=r['decision_valid'],statistics=r['statistics']))
 for x in r['results']:
  rows.append(dict(symbol=symbol,open_bps=x['open_bps'],close_bps=x['close_bps'],buys=x['buys'],sells=x['sells'],flips=x['flips'],cycles=x['completed_cycles'],pnl=float(x['binance_mark_pnl_usdg']),hold=float(x['hold_pnl_usdg']),excess=float(x['excess_vs_hold_usdg']),cycle_excess=float(x['cycle_excess_usdg']),turnover=float(x['turnover_usdg']),open_episode=x['open_episode_at_end'],rejections=sum(x['cancelled'].values()),rapid_cycles=sum(a['duration_ns']<1_000_000_000 for a in x['cycles'])))
(B/'summary.json').write_text(json.dumps(dict(rows=rows,quality=quality),indent=2)+'\n')
lines=['# Separate open/close thresholds, including negative close','',
'Exploratory replay of 2026-11-15 23:55–2026-11-16 01:55 UTC. Each pool starts independently with approximately 500 USDG of base tokens, zero cash. Open sells the available token inventory; close buys maximum affordable token exposure up to the 500 USDG position cap. Closing does not guarantee restoration of the original token count. No shorting, hedging, or fixed holding time.',
'', 'Open and close refer to episode phase, not fixed buy/sell labels. Phase advances only on a filled order, not on submission or rejection. A negative close threshold permits a negative instantaneous edge relative to Binance; it is not a bound on episode loss. For a buyback, edge = quantity × Binance bid / pool cost − 1. A −5 bps close allows buying about 5 bps above the reference bid. A negative threshold does not change the positive opening requirement. Buy size is reduced against the local pool quote when necessary to fit available cash.',
'', 'Both Taiwan receipt timestamps are translated to Ohio (Binance +100 ms, chain −175 ms), with 20 ms decision-to-chain arrival and immediate execution assumed. One-way network assumptions: Tokyo→Taiwan 25 ms, Tokyo→Ohio 125 ms, chain→Taiwan 175 ms, local chain feed 0 ms. Submitted slippage limit 1 bps; pool fees and per-fill size impact included; gas and revert costs zero; USDG/USDT parity assumed.',
'', 'Only the six pools with prior successful-swap price errors below 0.01 bps are included. This is conditional source-calibrated replay: provider guards/fallbacks are incomplete. Own fills do not persist into future historical pool states. That approximation is especially material for rapid repeated cycles. Larger flip counts must not be treated as confirmed executable profits.',
'', 'One completed cycle is one filled opening sale followed by one filled closing buy. A final sale with no buyback is an open episode. PnL includes terminal inventory marked at Binance bid. Excess vs hold compares the entire strategy with holding initial inventory. Cycle excess compares each closed episode with holding its opening inventory through its close, valued at then-available Binance bid; it is not cash-only realized profit. Turnover counts both legs.',
'', '| Pool | Open bps | Close bps | Cycles | Flips | PnL USDG | Excess vs hold USDG | Turnover USDG | Subsecond cycles |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for r in rows:lines.append(f"| {r['symbol']} | {r['open_bps']} | {r['close_bps']} | {r['cycles']} | {r['flips']} | {r['pnl']:+.6f} | {r['excess']:+.6f} | {r['turnover']:.2f} | {r['rapid_cycles']} |")
lines+=['','The grid was frozen before examining new-capture results. The new 24-hour tape is reserved for separate evaluation; the old two-hour grid is in-sample research, not an out-of-sample profitability claim. Same-tape best rows must not be represented as selected production parameters.','', 'New capture: `'+frozen['new_capture']['directory']+'`. This is a binary+zstd raw tape plus initial sparse checkpoint, not a live verified bid/ask stream. Future replay must check coverage and gaps before using the new segment.','', 'Artifacts: `frozen-grid.json`, `summary.json`, and per-pool `*-backtest.json` / `*-config.json`.']
overview=['## Observed result','','Negative close thresholds produce completed cycles, but do not consistently improve PnL. SPCX open 5 / close −5 completes one cycle and then opens another sale; its first cycle lasts approximately 59.7 minutes. This is not evidence of a rapid, repeatable latency trade. Open 5 / close −10 completes two cycles, but their combined excess versus episode hold is negative even though final portfolio PnL is positive.','', '| SPCX open bps | Close bps | Completed cycles | Final marked PnL USDG | Open episode at end |','|---|---:|---:|---:|---|']
for o,c in [('5','0'),('5','-5'),('5','-10'),('10','0'),('10','-20')]:
 r=next(x for x in rows if x['symbol']=='SPCXBUSDT'and x['open_bps']==o and x['close_bps']==c)
 overview.append(f"| {o} | {c} | {r['cycles']} | {r['pnl']:+.6f} | {r['open_episode']} |")
overview+=['','Very negative close thresholds can overlap with opening conditions and create repeated spread/fee payments. SPY open 2 / close −20 produces 3,268 simulated cycles, mostly subsecond, and approximately −491 USDG marked PnL. This is a churn diagnostic under a non-persistent-own-impact model, not an estimate of actual executable trade count.','']
lines=lines[:2]+overview+lines[2:]
(B/'OPEN-CLOSE-RESULTS.md').write_text('\n'.join(lines)+'\n')
for symbol in frozen['symbols']:
 a=[r for r in rows if r['symbol']==symbol]
 if a:print(symbol,'most cycles',max(a,key=lambda r:r['cycles']),'best pnl',max(a,key=lambda r:r['pnl']))
