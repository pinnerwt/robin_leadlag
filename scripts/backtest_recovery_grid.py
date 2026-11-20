"""Checkpoint-separated, offline latency/threshold sweep; no cross-gap portfolio."""
import argparse,copy,json,time,concurrent.futures
from pathlib import Path
import causal_spcx_backtest as bt

def run_task(task):
 segment,m,base=task;d=Path(segment['directory']);symbol=m['symbol'];outpath=d/(symbol+('-buy' if base.get('entry_side')=='buy' else '')+('-full-grid.json' if base.get('provider_mode')=='provider-full' else '-grid.json'))
 if outpath.exists():return
 audit=json.load(open(d/'extraction-audit.json'));failures=[x for x in audit if x.get('symbol',symbol)==symbol]
 end=min([segment['end_ns']]+[x['mono_ns']-5_000_000_000 for x in failures]);start=segment['ready_ns']
 if end-start<30_000_000_000:
  outpath.write_text(json.dumps(dict(symbol=symbol,status='excluded_insufficient_continuity',start_ns=start,end_ns=end,extraction_failures=failures),indent=2));return
 c=copy.deepcopy(base);c.update(checkpoint=m['seed'],symbol=symbol,warmup_seconds=start/1e9,initial_inventory_usdg='0' if base.get('entry_side')=='buy' else '500',initial_cash_usdg='500' if base.get('entry_side')=='buy' else '0',entry_side=base.get('entry_side','sell'),cache_no_order=True,diagnostic_probes=False,share_candidate_evaluations=True)
 es=[r for r in map(json.loads,open(d/(symbol+'-events.jsonl')))if r.get('mono_ns',0)<=end]
 # Keep actual quote-change times plus the final unchanged observation before
 # every change/event. Unchanged BBO refreshes are otherwise retained: freshness matters.
 bs=[r for r in map(json.loads,open(d/(symbol+'-bbo.jsonl')))if r['mono_ns']<=end]
 out=dict(symbol=symbol,generation=segment['generation'],start_ns=start,end_ns=end,config=c,extraction_failures=failures)
 try:
  r=bt.run(c,c['routes'][0],es,bs);out['run']=r
  err=r['statistics'].get('max_observed_price_error_bps',0)
  out['status']='state_failed'if not(r['truth_valid']and r['decision_valid'])else('conditional_small_error'if err<=1 else'approximate_only')
  for x in r['results']:
   sides=[f['side']for f in x['fills']];x.update(buys=sides.count('buy'),sells=sides.count('sell'),flips=sum(a!=b for a,b in zip(sides,sides[1:])),completed_cycles=len(x['cycles']))
  print(d.name,symbol,out['status'],'seconds',round(r['wall_seconds'],1),'max_cycles',max(x['completed_cycles']for x in r['results']),'error_bps',err,flush=True)
 except Exception as e:out.update(status='error',error=repr(e));print(d.name,symbol,out['error'],flush=True)
 tmp=outpath.with_suffix('.tmp');tmp.write_text(json.dumps(out,indent=2)+'\n');tmp.replace(outpath)

def main():
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--jobs',type=int,default=3);p.add_argument('--only-segment');p.add_argument('--ready-only',action='store_true');p.add_argument('--provider-mode',choices=['source-only','provider-full'],default='source-only');p.add_argument('--entry-side',choices=['buy','sell'],default='sell');a=p.parse_args()
 base=json.load(open('config/spcx-ohio-translated-backtest.json'));base['provider_mode']=a.provider_mode;base['entry_side']=a.entry_side
 for k in ('initial_position_tokens','initial_mark_price_usdg'):base.pop(k,None)
 frozen=json.load(open('reports/metric-multi-latest/open-close/frozen-grid.json'))['grid']
 base.update(routes=[dict(name='taiwan_effective_latency_grid',chain_shift_ms=0,truth_chain_shift_ms=0,binance_shift_ms=0,execution_ms=220)],open_close_grid=[dict(g,execution_ms=ms)for ms in range(200,261,10)for g in frozen])
 base['route_assumptions']='200..260ms total effective signal-to-fill delay on Taiwan receipt timeline. No additional feed shifts. Sensitivity proxy, not a measured Ohio deployment.'
 base['initial_inventory_assumption']=('500 USDG cash, zero tokens' if a.entry_side=='buy' else '500 USDG base inventory, zero cash')+' independently at each recovered segment. Isolated episodes, not a continuous portfolio.'
 (a.directory/('grid-config-'+a.entry_side+'-'+a.provider_mode+'.json')).write_text(json.dumps(base,indent=2)+'\n');segments=json.load(open(a.directory/'segments.json'))
 if a.ready_only:
  progress=(a.directory/'extract-progress.log').read_text().splitlines();complete=[int(line.split()[1])for line in progress if line.startswith('finished ')];segments=segments[:max(complete)+1] if complete else []
 if a.only_segment:segments=[s for s in segments if Path(s['directory']).name==a.only_segment]
 tasks=[]
 for s in segments:
  if not(Path(s['directory'])/'extraction-audit.json').exists():raise ValueError('extraction incomplete')
  tasks.extend((s,m,base)for m in json.load(open(Path(s['directory'])/'manifest.json')))
 with concurrent.futures.ProcessPoolExecutor(max_workers=a.jobs)as ex:list(ex.map(run_task,tasks))
if __name__=='__main__':main()
