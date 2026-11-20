"""Offline per-pool scenario sweep. Results are exploratory, not selected OOS policies."""
import json,time,concurrent.futures,argparse
from pathlib import Path
import causal_spcx_backtest as bt
CALIBRATED=False
BASE=Path('reports/metric-multi-latest')
def run_pool(m):
 symbol=m['symbol'];c=json.load(open('config/spcx-ohio-translated-backtest.json'))
 for k in ('initial_position_tokens','initial_mark_price_usdg'):c.pop(k,None)
 c.update(cache_no_order=True,diagnostic_probes=False,checkpoint=m['seed'],symbol=symbol,events=str(BASE/(symbol+'-events.jsonl')),bbo_tape=str(BASE/(symbol+'-bbo.jsonl')),initial_inventory_usdg='500',initial_cash_usdg='0',edges_bps=['0','2','5','10','15','20','25','30'])
 c['initial_inventory_assumption']='Each pool starts with 500 USDG worth of its own token at first available Binance ask, cash zero. Separate pool portfolios, not a shared 500 USDG portfolio.'
 c['threshold_grid']=[dict(buy_bps=x,sell_bps=x) for x in c['edges_bps']]+[dict(buy_bps='10',sell_bps=x) for x in ('0','2','5')]+[dict(buy_bps=x,sell_bps='10') for x in ('0','2','5')]
 (BASE/(symbol+('-calibrated-config.json' if CALIBRATED else '-config.json'))).write_text(json.dumps(c,indent=2))
 events=[json.loads(l) for l in open(c['events'])];bbos=[json.loads(l) for l in open(c['bbo_tape'])]
 out=dict(symbol=symbol,pool=m['pool'],config=c)
 try:
  r=bt.run(c,c['routes'][0],events,bbos)
  for x in r['results']:
   sides=[f['side'] for f in x['fills']]
   x['buys']=sides.count('buy');x['sells']=sides.count('sell');x['flips']=sum(a!=b for a,b in zip(sides,sides[1:]));x['buyback_episodes']=sum(a=='sell' and b=='buy' for a,b in zip(sides,sides[1:]))
   x['turnover_usdg']=str(sum((bt.D(f['amount_usdg']) for f in x['fills']),bt.D(0)))
  out['run']=r
 except Exception as e:out['error']=repr(e)
 (BASE/(symbol+('-calibrated-backtest.json' if CALIBRATED else '-backtest.json'))).write_text(json.dumps(out,indent=2)+'\n')
 print(symbol, 'ERROR '+out['error'] if 'error'in out else [(x['edge_bps'],x['exit_edge_bps'],x['buys'],x['sells'],x['flips'],round(float(x['binance_mark_pnl_usdg']),4)) for x in out['run']['results']],flush=True)
 return dict(symbol=symbol,error=out.get('error'))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--calibrated',action='store_true');p.add_argument('--symbols',nargs='*');p.add_argument('--jobs',type=int,default=2);a=p.parse_args();CALIBRATED=a.calibrated;manifest=json.load(open(BASE/('calibrated-manifest.json' if CALIBRATED else 'manifest.json')))
 if a.symbols:manifest=[m for m in manifest if m['symbol']in a.symbols]
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:list(ex.map(run_pool,manifest))
