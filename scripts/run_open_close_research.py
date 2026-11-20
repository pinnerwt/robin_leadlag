"""Frozen open/close threshold grid; sell-first inventory strategy, offline only."""
import json,concurrent.futures,datetime
from pathlib import Path
import causal_spcx_backtest as bt
B=Path('reports/metric-multi-latest');O=B/'open-close';O.mkdir(exist_ok=True)
GRID=[dict(open_bps=str(o),close_bps=str(c))for o in (2,5,10,15,20,25,30)for c in sorted(set([o,0,-5,-10,-20]+([5]if o>=5 else [])),reverse=True)]
SYMBOLS=['SPCXBUSDT','METABUSDT','TSLABUSDT','GOOGLBUSDT','AAPLBUSDT','SPYBUSDT']
def run(symbol):
 c=json.load(open(B/(symbol+'-calibrated-config.json')));c.update(open_close_grid=GRID,entry_side='sell',cache_no_order=True,diagnostic_probes=False)
 c.pop('threshold_grid',None)
 seed=json.load(open(c['checkpoint']));word_id=seed['pools'][0]['word_id']
 c['binding_assumption']=f'Direct compressed word ID {word_id:#x} maps to {symbol} from the pinned source-contract storage; no future acceptance filtering in signals.'
 c['threshold_mode']='episode: open sells initial token exposure; close buys maximum affordable exposure up to the position cap'
 c['initial_inventory_assumption']='Approximately 500 USDG of base tokens, zero cash. Close restores affordable base exposure up to the 500 USDG cap, not necessarily the original token quantity.'
 (O/(symbol+'-config.json')).write_text(json.dumps(c,indent=2)+'\n')
 es=[json.loads(l)for l in open(c['events'])];bs=[json.loads(l)for l in open(c['bbo_tape'])]
 r=bt.run(c,c['routes'][0],es,bs)
 for x in r['results']:
  sides=[f['side']for f in x['fills']];x['flips']=sum(a!=b for a,b in zip(sides,sides[1:]));x['buys']=sides.count('buy');x['sells']=sides.count('sell');x['completed_cycles']=len(x['cycles']);x['turnover_usdg']=str(sum((bt.D(f['amount_usdg'])for f in x['fills']),bt.D(0)));x['cycle_excess_usdg']=str(sum((bt.D(a['excess_vs_episode_hold_usdg'])for a in x['cycles']),bt.D(0)))
 out=dict(config=c,run=r);(O/(symbol+'-backtest.json')).write_text(json.dumps(out,indent=2)+'\n')
 print(symbol,'valid',r['truth_valid'],r['decision_valid'],'max_cycles',max(x['completed_cycles']for x in r['results']),'best_pnl',max(float(x['binance_mark_pnl_usdg'])for x in r['results']),flush=True)
 return symbol
if __name__=='__main__':
 (O/'frozen-grid.json').write_text(json.dumps(dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),symbols=SYMBOLS,grid=GRID,initial_side='sell',new_capture=json.load(open('reports/active-metric-capture.json')),out_of_sample='Evaluate new capture with the same grid and separately report preselected policies. No new capture results used to select this grid.'),indent=2)+'\n')
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as ex:list(ex.map(run,SYMBOLS))
