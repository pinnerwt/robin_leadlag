import sys,json,concurrent.futures
from pathlib import Path
from decimal import Decimal,ROUND_DOWN
sys.path.insert(0,'scripts')
import causal_spcx_backtest as bt
R=Path('reports/ohio-latest-20261119T2103Z')
def task(m):
 symbol=m['symbol'];ticker=symbol.removesuffix('BUSDT');w=json.load(open(R/'window.json'));origin=w['origin_ns']
 rows=[json.loads(l)for l in open(Path('reports/ohio-iex-first-20261119')/(ticker+'-iex-bbo.jsonl'))];rows=[r for r in rows if w['start_ns']<=r['recv_ns']<=w['end_ns']]
 c=json.load(open('config/spcx-ohio-translated-backtest.json'));c.update(checkpoint=str(R/(symbol+'-seed.json')),symbol=symbol,provider_mode='provider-full',quote_only=True,hy_fixed_quantity=str((Decimal(500)/Decimal(rows[0]['ask'])).quantize(Decimal('1e-18'),rounding=ROUND_DOWN)),warmup_seconds=(w['start_ns']-origin)/1e9,return_invalid_diagnostics=True)
 route=dict(name='ohio',chain_shift_ms=0,truth_chain_shift_ms=0,binance_shift_ms=0,execution_ms=20)
 events=[json.loads(l)for l in open(R/(symbol+'-events.jsonl'))];bbos=[dict(rows[0],mono_ns=w['start_ns']-origin),dict(rows[-1],mono_ns=w['end_ns']-origin)];quotes=[]
 def observe(ns,q,v):quotes.append([ns,str(q),v.get('bid_usdg'),v.get('ask_usdg'),v['status'],v.get('reason')])
 result=bt.run(c,route,events,bbos,pool_observer=observe)
 (R/(ticker+'-pool-quotes.json')).write_text(json.dumps(quotes));(R/(ticker+'-quote-clock-audit.json')).write_text(json.dumps(dict(fixed_quantity=c['hy_fixed_quantity'],observations=len(quotes),**result),indent=2));print(ticker,len(quotes),result,flush=True)
if __name__=='__main__':
 rows=[r for r in json.load(open(R/'manifest.json'))if r['symbol']!='ETHUSDT']
 with concurrent.futures.ProcessPoolExecutor(max_workers=2) as ex:list(ex.map(task,rows))
