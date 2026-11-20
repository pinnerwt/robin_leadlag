"""Offline Ohio candidate-source sweep with full provider expiry checks."""
import argparse,collections,datetime,json,math
from pathlib import Path
import causal_spcx_backtest as bt
from tape import records

ROOT=Path('reports/ohio-20ms-backtest')
START=1795059181000000000
END=1795060981000000000
SOURCES=[('ETH','ETHUSDT','binance'),('ETH','ETHUSDT','bybit'),('NVDA','NVDABUSDT','bybit')]

def positive_leads(path='reports/ohio-halfhour-20261119T040301Z/hy.json'):
 rows=[]
 for r in json.loads(Path(path).read_text())['results']:
  if r['y']!='robinhood_source' or r['side']!='mid' or r['full'].get('status')!='ok' or r['full']['peak_ms']<=0:continue
  ticker=r['ticker'];folds=r['folds']['10'];valid=[f for f in folds if f.get('status')=='ok']
  rows.append(dict(ticker=ticker,symbol='ETHUSDT' if ticker=='ETH' else ticker+'BUSDT',venue=r['x'],peak_ms=r['full']['peak_ms'],positive_folds=sum(f['peak_ms']>0 for f in valid),valid_folds=len(valid),boundary=r['full']['boundary'],gap5s_peak_ms=r['gap5s_sensitivity'].get('peak_ms'),descriptive_stability='9+ positive folds' if sum(f['peak_ms']>0 for f in valid)>=9 else 'unstable'))
 return rows

def load_bbos(rows,sources,origins,start,end):
 streams={(t,v):[] for t,s,v in sources};symbols={t:s for t,s,v in sources};latest={};quality=collections.Counter()
 for r in rows:
  if r.get('kind')!='equity_bbo' or not start<=r['recv_ns']<=end:continue
  key=(r['ticker'],r['venue'])
  if key not in streams:continue
  if r.get('is_late'):quality['late_sequence']+=1;continue
  if r['venue']=='kraken':
   whole,_,fraction=r['exchange_timestamp'].removesuffix('Z').partition('.')
   stamp=int(datetime.datetime.strptime(whole,'%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp())*10**9+int(fraction.ljust(9,'0'))
   if stamp<latest.get(key,0):quality['kraken_stale_source']+=1;continue
   if r.get('message_type')=='snapshot' and key in latest:quality['kraken_repeat_snapshot']+=1;continue
   latest[key]=stamp
  bid,ask=float(r['bid']),float(r['ask'])
  if not(math.isfinite(bid) and math.isfinite(ask) and 0<bid<=ask):raise ValueError('Invalid BBO requires explicit gap handling')
  streams[key].append(dict(mono_ns=r['recv_ns']-origins[symbols[r['ticker']]],bid=str(r['bid']),ask=str(r['ask'])))
  quality['accepted_'+r['venue']+'_'+r['ticker']]+=1
 return streams,dict(quality)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--only');ap.add_argument('--entry-side',choices=['buy','sell']);ap.add_argument('--preflight',action='store_true');ap.add_argument('--all-leads',action='store_true');a=ap.parse_args()
 selection=positive_leads() if a.all_leads else None
 sources=[(r['ticker'],r['symbol'],r['venue']) for r in selection] if selection else SOURCES
 if selection:(ROOT/'all-leads-selection.json').write_text(json.dumps(selection,indent=2)+'\n')
 origins={}
 for ticker,symbol,venue in sources:
  session=next(json.loads(l) for l in open(ROOT/(symbol+'-events.jsonl')) if json.loads(l)['kind']=='session');origins[symbol]=session['start_utc_ns']
 paths=sorted(Path('captures/ohio-halfhour-20261119T040301Z').glob('ohio-equity-*.bin.zst'))
 streams,quality=load_bbos(records(paths),sources,origins,START,END)
 if a.all_leads:(ROOT/'all-leads-bbo-quality.json').write_text(json.dumps(quality,indent=2)+'\n')
 # Retain all refreshes: freshness is a causal policy input. Quote caching avoids redundant EVM work.
 for ticker,symbol,venue in sources:
  name=ticker+'-'+venue
  if a.only and a.only!=name:continue
  for side in ([a.entry_side] if a.entry_side else ['buy','sell']):
   output=ROOT/(name+'-'+side+('-preflight' if a.preflight else '')+'.json')
   if output.exists():continue
   config=json.load(open('config/spcx-ohio-translated-backtest.json'))
   for k in ('initial_position_tokens','initial_mark_price_usdg'):config.pop(k,None)
   config.update(checkpoint=str(ROOT/(symbol+'-seed.json')),symbol=symbol,provider_mode='provider-full',return_invalid_diagnostics=True,warmup_seconds=(START-origins[symbol])/1e9,initial_inventory_usdg='500' if side=='sell' else '0',initial_cash_usdg='500' if side=='buy' else '0',entry_side=side,cache_no_order=True,diagnostic_probes=False,share_candidate_evaluations=True,
    routes=[dict(name='measured_ohio_ingress_exec20',chain_shift_ms=0,truth_chain_shift_ms=0,binance_shift_ms=0,execution_ms=20)],
    open_close_grid=[dict(open_bps=str(o),close_bps=str(c)) for o in ([10] if a.preflight else [10,15,20,25,30]) for c in ([0] if a.preflight else [-10,-5,0,5])])
   config.update(route_assumptions='Actual Ohio receipt timestamps for both streams; no Taiwan translation.',binding_assumption='Tracked compressed word IDs; auxiliary oracle payloads decoded under assumed-success calldata policy. No signature verification.',initial_inventory_assumption='Buy-first starts with 500 USDG cash; sell-first starts with 500 USDG worth of tokens at first source ask.',calldata_clock='Ohio first relay receipt mapped to recorder clock')
   print(name,side,'starting',flush=True)
   es=[json.loads(l) for l in open(ROOT/(symbol+'-events.jsonl'))]
   result=dict(config=config,source_venue=venue,scope='full-provider local replay; historical pool state price-taker simulation; USD/USDT parity and zero gas; no persistent own fill impact')
   try:result['run']=bt.run(config,config['routes'][0],es,streams[(ticker,venue)])
   except Exception as exc:result['error']=repr(exc)
   output.write_text(json.dumps(result,indent=2)+'\n')
   run=result.get('run',{});print(name,side,'valid',run.get('truth_valid'),run.get('decision_valid'),'fills',[len(s['fills']) for s in run.get('results',[])], 'stats',run.get('statistics'),result.get('error'),flush=True)
if __name__=='__main__':main()
