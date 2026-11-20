"""Summarize exploratory multi-pool fixed policy grids without picking a live policy."""
import json,sys
from pathlib import Path
B=Path('reports/metric-multi-latest')
CALIBRATED='--calibrated' in sys.argv
rows=[];coverage=[]
for m in json.load(open(B/'manifest.json')):
 p=B/(m['symbol']+('-calibrated-backtest.json' if CALIBRATED else '-backtest.json'))
 if not p.exists():coverage.append(dict(symbol=m['symbol'],error='not finished'));continue
 d=json.loads(p.read_text())
 if 'error'in d:coverage.append(dict(symbol=m['symbol'],error=d['error']));continue
 r=d['run'];stats=r['statistics']
 coverage.append(dict(symbol=m['symbol'],truth_valid=r['truth_valid'],decision_valid=r['decision_valid'],statistics=stats,quote_errors=r['decision_quote_errors']))
 for x in r['results']:
  rows.append(dict(symbol=m['symbol'],buy_bps=x['edge_bps'],sell_bps=x['exit_edge_bps'],buys=x['buys'],sells=x['sells'],flips=x['flips'],buybacks=x['buyback_episodes'],pnl=float(x['binance_mark_pnl_usdg']),hold=float(x['hold_pnl_usdg']),excess=float(x['excess_vs_hold_usdg']),turnover=float(x['turnover_usdg']),rejected=sum(x['cancelled'].values()),valid=r['truth_valid'] and r['decision_valid'],swap_mismatches=stats.get('observed_swap_token_mismatch',0)))
(B/('calibrated-summary.json' if CALIBRATED else 'summary.json')).write_text(json.dumps(dict(rows=rows,coverage=coverage),indent=2)+'\n')
print(json.dumps(dict(coverage=coverage,with_flips=[r for r in rows if r['flips']]),indent=2))
