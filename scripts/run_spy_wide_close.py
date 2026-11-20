"""Post-hoc SPY close-threshold exploration; not untouched validation."""
import json,concurrent.futures,argparse
from pathlib import Path
from decimal import Decimal as D,ROUND_FLOOR
import causal_spcx_backtest as bt
R=Path('reports/ohio-latest-20261119T2103Z')
def task(args):
 row,segment,side=args;ticker=row['symbol'].removesuffix('BUSDT');tag=f'{ticker}-{segment}-{side}-wide-close';path=R/(tag+'.json');w=json.load(open(R/'window.json'));origin=w['origin_ns'];start=w['start_ns'] if segment=='train' else w['split_ns'];end=w['split_ns']-1 if segment=='train' else w['end_ns']
 c=json.load(open('config/spcx-ohio-translated-backtest.json'))
 for k in ('initial_mark_price_usdg','initial_position_tokens'):c.pop(k,None)
 bbos=[json.loads(l) for l in open(R/(ticker+'-iex-bbo.jsonl'))];first=next(r for r in bbos if not r.get('invalid'));baseline=str((D(500)/D(first['ask'])).quantize(D('1e-18'),rounding=ROUND_FLOOR));bbos=[r for r in bbos if start<=r['recv_ns']<=end]
 c.update(checkpoint=str(R/(row['symbol']+'-seed.json')),symbol=row['symbol'],provider_mode='provider-full',fixed_baseline=True,initial_position_tokens=baseline,initial_inventory_usdg='0',initial_cash_usdg='500',entry_side=side,warmup_seconds=(start-origin)/1e9,return_invalid_diagnostics=True,cache_no_order=True,diagnostic_probes=False,share_candidate_evaluations=True,open_close_grid=[dict(open_bps=str(o),close_bps=str(cl))for o in (10,)for cl in (-15,-20,-25,-30)])
 route=dict(name='ohio_iex_exec20',chain_shift_ms=0,truth_chain_shift_ms=0,binance_shift_ms=0,execution_ms=20);c['routes']=[route];events=[r for r in map(json.loads,open(R/(row['symbol']+'-events.jsonl')))if r.get('mono_ns',0)<=end-origin]
 print('start',tag,len(events),len(bbos),flush=True);out=dict(ticker=ticker,pool=row['pool'],segment=segment,side=side,config=c)
 try:out['run']=bt.run(c,route,events,bbos)
 except Exception as exc:out['error']=repr(exc)
 path.write_text(json.dumps(out,indent=2)+'\n');v=out.get('run',{});print('done',tag,v.get('truth_valid'),v.get('decision_valid'),max([len(x['fills'])for x in v.get('results',[])],default=0),out.get('error'),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--only');a=p.parse_args();rows=[r for r in json.load(open(R/'manifest.json'))if r['symbol']!='ETHUSDT' and (not a.only or r['symbol']==a.only+'BUSDT')]
 with concurrent.futures.ProcessPoolExecutor(max_workers=2) as ex:list(ex.map(task,[(r,s,d)for r in rows for s in ('train','test')for d in ('sell',)]))
