"""Summarize observed Ohio threshold sweeps; separate realized and marked PnL."""
import json,statistics
from pathlib import Path
B=Path('reports/ohio-20ms-backtest');summary=[]
lines=['# Ohio 20 ms threshold replay','',
'Window: 2026-11-19 03:33:01–04:03:01 UTC; ETH starts when its first BBO arrives (about 27.8 minutes). The last complete equity record is 04:02:38.631 UTC.',
'', '500 USDG maximum token exposure; buy-first starts with 500 USDG cash, sell-first with 500 USDG of tokens valued at the first source ask. Open thresholds 10/15/20/25/30 bps; close thresholds -10/-5/0/5 bps; no timed exit and no hedge.',
'', 'Buy edge = source bid × token quantity / pool ask cost − 1. Sell edge = pool bid proceeds / (source ask × token quantity) − 1. Edges are in bps. A negative close threshold permits paying up to that disadvantage against the source to exit.',
'', 'Both streams use actual Ohio receipt timestamps with zero geographic shifts. Execution uses state at signal + 20 ms. Pool fee and immediate size impact are included; submitted limit tolerates 1 bp, BBO freshness limit is 1 s. No extra compute/signing/sequencer queue delay is modeled.',
'', '## Replay validation','',
'The old source-only updater omitted the auxiliary Pyth oracle at 0x30a88…7102. Both oracle calldata streams now update local state before full provider and pool simulation. No remote RPC was used.',
'', 'Auxiliary decoder: 3,280 post-checkpoint transactions, 10,289 tracked feed advances, zero mismatches against pushed FeedUpdated IDs. Logs are retrospective validation, not signal inputs. Payload signature verification is not implemented; successful calldata is assumed at decision time.',
'', 'Full-prefix swap validation: NVDA 272 swaps, zero token-delta or price mismatches. ETH 788 swaps, 27 token-delta mismatches, maximum price error 1.000025 bps. ETH results are approximate at this precision; recorded bin deltas reconcile depth. Policy evaluation ends earlier than the chain prefix, so its swap counts are slightly smaller.',
'', '## Results','',
'Realized PnL excludes gas/revert costs. Marked PnL includes remaining tokens valued at source bid, not a pool liquidation. Each row is an independent simulation; rows must not be added together. Sell-first is measured against holding the initial inventory.']
for name in ['ETH-binance','ETH-bybit','NVDA-bybit']:
 for side in ['buy','sell']:
  path=B/(name+'-'+side+'.json');root=json.load(open(path));r=root['run'];assert r['truth_valid'] and r['decision_valid']
  root['config'].update(route_assumptions='Actual Ohio receipt timestamps for both streams; no Taiwan translation.',binding_assumption='Tracked compressed word IDs; auxiliary oracle payloads decoded under assumed-success calldata policy. No signature verification.',initial_inventory_assumption='Buy-first starts with 500 USDG cash; sell-first starts with 500 USDG worth of tokens at first source ask.',calldata_clock='Ohio first relay receipt mapped to recorder clock')
  path.write_text(json.dumps(root,indent=2)+'\n')
  lines+=['',f'### {name}: {side}-first','', '| Open bps | Close bps | Fills | Completed cycles | Realized USDG | Marked excess vs hold USDG | Inventory episode open | Rejections |','|---:|---:|---:|---:|---:|---:|:---:|---:|']
  for s in r['results']:
   for f in s['fills']:assert f['fill_ns']-f['signal_ns']==20_000_000
   row=dict(source=name,entry_side=side,open_bps=s['open_bps'],close_bps=s['close_bps'],fills=len(s['fills']),cycles=len(s['cycles']),realized_usdg=float(s['realized_pnl_usdg']),marked_excess_usdg=float(s['excess_vs_hold_usdg']),open_at_end=s['open_episode_at_end'],rejections=s['cancelled']);summary.append(row)
   lines.append(f"| {row['open_bps']} | {row['close_bps']} | {row['fills']} | {row['cycles']} | {row['realized_usdg']:.6f} | {row['marked_excess_usdg']:.6f} | {row['open_at_end']} | {sum(row['rejections'].values())} |")
  unique={ (f['signal_ns'],f['side'],f['size_tokens']):f for s in r['results'] for f in s['fills']}
  if unique:
   lines+=['','Provider age across successful simulated operations (deduplicated scenario fills), measured from stored publish timestamp:','','| Age field | Minimum ms | Median ms | Maximum ms |','|---|---:|---:|---:|']
   for key in ['signal_source_age_ms','execution_source_age_ms','provider_block_source_age_ms','signal_aux_age_ms','execution_aux_age_ms','provider_block_aux_age_ms']:
    vals=[f[key] for f in unique.values()];lines.append(f'| {key} | {min(vals):.3f} | {statistics.median(vals):.3f} | {max(vals):.3f} |')
  lines+=['',f"Decision provider quote errors: `{r['decision_quote_errors']}`. Execution quote errors: `{r['execution_quote_errors']}`."]
lines+=['','## Expiry findings','',
'Independent frozen-price probes keep the other oracle fresh: for ETH and NVDA, the main source accepts exactly 10,000 ms and rejects 10,001 ms; the auxiliary source accepts 15,000 ms and rejects 15,001 ms. These are checkpoint-specific contract tests, not a generic network delay rule.',
'', 'Contract age uses integer block.timestamp × 1000 minus the millisecond publish timestamp. Wall-clock age at the machine is reported separately. Negative contract ages within a second can arise from timestamp quantization; they do not mean the strategy saw a future message.',
'', 'No provider-expiry rejection occurred in this evaluated window. Bybit ETH has submitted-limit rejections in two scenarios; these are not expiry errors. There are too few completed cycles to infer robust profitability.',
'', '## Limitations','',
'In-sample, short overnight window. USDG/USD/USDT parity is assumed. No gas, revert costs, funding/allowance/router acceptance, queue competition or persistent own-trade changes to future historical depth. Full provider checks are exercised, but full transaction execution is not simulated. Do not interpret unrealized marked gains or HY correlation as locked-in arbitrage profit.',
'', 'Artifacts: six source/direction JSON files contain all orders, fills, rejects and ages; summary.json contains all 120 scenario rows; isolated-provider-expiry.json contains boundary probes; auxiliary-acceptance-audit.json and *-aux-audit.json contain replay validation.']
(B/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(B/'RESULTS.md').write_text('\n'.join(lines)+'\n')
print('wrote',len(summary),'scenario rows')
