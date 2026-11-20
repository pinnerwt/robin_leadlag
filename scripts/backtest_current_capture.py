"""Run the previously frozen episode grid on every pool in a new safe tape prefix."""
import argparse,copy,json,concurrent.futures
from pathlib import Path
import causal_spcx_backtest as bt
p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--jobs',type=int,default=3);a=p.parse_args();B=Path(a.base);O=B/'open-close';O.mkdir(exist_ok=True)
FROZEN=json.load(open('reports/metric-multi-latest/open-close/frozen-grid.json'))
manifest=json.load(open(B/'calibrated-manifest.json'))
BASE=json.load(open('config/spcx-ohio-translated-backtest.json'))
def run(m):
 symbol=m['symbol'];c=copy.deepcopy(BASE)
 for k in ('initial_position_tokens','initial_mark_price_usdg'):c.pop(k,None)
 c.update(symbol=symbol,checkpoint=m['seed'],events=str(B/(symbol+'-events.jsonl')),bbo_tape=str(B/(symbol+'-bbo.jsonl')),initial_inventory_usdg='500',initial_cash_usdg='0',open_close_grid=FROZEN['grid'],entry_side='sell',cache_no_order=True,diagnostic_probes=False)
 c['binding_assumption']=f"Pinned source binding for {symbol}: word {m['word_id']:#x}. Sender recovery is intentionally omitted; signals do not depend on future acceptance logs."
 c['initial_inventory_assumption']='Each pool separately starts with approximately 500 USDG of tokens and zero cash; no shared portfolio allocation. Initial mark is the first fresh BBO bid after warmup.'
 c['evaluation_note']='All frozen policies evaluated; choosing the best row on this new sample is not an independent test of that winning policy.'
 (O/(symbol+'-config.json')).write_text(json.dumps(c,indent=2)+'\n')
 es=[json.loads(l)for l in open(c['events'])];bs=[json.loads(l)for l in open(c['bbo_tape'])]
 out=dict(symbol=symbol,config=c)
 try:
  r=bt.run(c,c['routes'][0],es,bs)
  for x in r['results']:
   sides=[f['side']for f in x['fills']];x['flips']=sum(a!=b for a,b in zip(sides,sides[1:]));x['buys']=sides.count('buy');x['sells']=sides.count('sell');x['completed_cycles']=len(x['cycles']);x['turnover_usdg']=str(sum((bt.D(f['amount_usdg'])for f in x['fills']),bt.D(0)))
  out['run']=r
 except Exception as e:out['error']=repr(e)
 path=O/(symbol+'-backtest.json');tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(out,indent=2)+'\n');tmp.replace(path)
 if 'run'in out:print(symbol,'valid',r['truth_valid'],r['decision_valid'],'max_cycles',max(x['completed_cycles']for x in r['results']),'max_error',r['statistics'].get('max_observed_price_error_bps',0),flush=True)
 else:print(symbol,out['error'],flush=True)
 return symbol
if __name__=='__main__':
 (O/'frozen-grid.json').write_text(json.dumps(FROZEN,indent=2)+'\n')
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs)as ex:list(ex.map(run,manifest))
