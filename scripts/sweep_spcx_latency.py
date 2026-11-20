"""Offline latency sensitivity with identical initial inventory and fixed thresholds."""
import copy,json,concurrent.futures
from pathlib import Path
import causal_spcx_backtest as bt
B=Path('reports/metric-multi-latest');O=B/'latency';O.mkdir(exist_ok=True)
c=json.load(open(B/'SPCXBUSDT-calibrated-config.json'));base=json.load(open(B/'SPCXBUSDT-calibrated-backtest.json'))['run']['initial_portfolio']
c.pop('initial_inventory_usdg',None);c.update(initial_position_tokens=base['base_tokens'],initial_mark_price_usdg=base['basis_price_usdg'],initial_cash_usdg=base['cash_usdg'],cache_no_order=True,edges_bps=['10','15'],threshold_grid=[dict(buy_bps=y,sell_bps=y)for y in ('10','15')])
c['initial_inventory_assumption']='Identical balance and initial valuation across all latency scenarios, taken from the completed Ohio 20 ms baseline.'
es=[json.loads(l)for l in open(c['events'])];bs=[json.loads(l)for l in open(c['bbo_tape'])]
def run(pair):
 x,d=pair;cfg=copy.deepcopy(c);route=cfg['routes'][0];route['name']=f'tokyo_ohio_{x}_execution_{d}';route['latency_ms']['tokyo_to_ohio']=x;route['latency_ms']['ohio_machine_to_chain']=d
 r=bt.run(cfg,route,es,bs);out=dict(config=cfg,run=r);(O/(route['name']+'.json')).write_text(json.dumps(out,indent=2)+'\n')
 print(x,d,[(a['edge_bps'],len(a['fills']),a['binance_mark_pnl_usdg'])for a in r['results']],flush=True)
 return dict(tokyo_ohio_ms=x,execution_ms=d,valid=r['truth_valid']and r['decision_valid'],results=r['results'])
if __name__=='__main__':
 pairs=[(125,d)for d in (0,10,20,40,60,80,100,125,150)]+[(x,20)for x in (75,100,150)]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as ex:rows=list(ex.map(run,pairs))
 (O/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
