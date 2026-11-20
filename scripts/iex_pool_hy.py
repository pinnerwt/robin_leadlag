"""Ohio IEX receipt-time HY versus separately labeled source and local pool quotes."""
import argparse,collections,json,math
from pathlib import Path
import numpy as np
from tape import records
from ohio_spot_hy import clean,scan

def load_iex(rows):
 series=collections.defaultdict(list);bbos=collections.defaultdict(list);quality=collections.Counter();latest={};seen={};symbols=[]
 for r in rows:
  kind=r.get('kind');t=r.get('recv_ns')
  if kind=='iex_session':symbols=r['config']['symbols']
  if kind in ('iex_gap','iex_stopped'):
   for symbol in symbols:series[symbol].append([t,float('nan'),float('nan')])
   quality[kind]+=1
  if kind!='iex_bbo':continue
  symbol=r['symbol'];stamp=r['exchange_ns'];b=float(r['bid']);a=float(r['ask']);quality['received_'+symbol]+=1
  if stamp<latest.get(symbol,0):quality['late_'+symbol]+=1;continue
  latest[symbol]=stamp;identity=(stamp,b,a)
  if seen.get(symbol)==identity:quality['duplicate_'+symbol]+=1;continue
  seen[symbol]=identity
  valid=math.isfinite(b) and math.isfinite(a) and 0<b<=a
  if not valid:quality['invalid_'+symbol]+=1;series[symbol].append([t,float('nan'),float('nan')]);continue
  series[symbol].append([t,b,a]);bbos[symbol].append(dict(recv_ns=t,exchange_ns=stamp,bid=str(r['bid']),ask=str(r['ask'])))
  quality['accepted_'+symbol]+=1
 return dict(series),dict(bbos),dict(quality)

def compare(x,y,start,end):
 if len(x)<10 or len(y)<10:return {'status':'insufficient_points'}
 x,xb=clean(np.asarray(x,dtype=float));y,yb=clean(np.asarray(y,dtype=float));duration=(end-start)/1e6
 full=scan(x,xb,y,yb,0,duration,step=2,limit=100,min_lag=1);wide=scan(x,xb,y,yb,0,duration,step=2,limit=500,min_lag=1)
 if wide:wide.pop('curve',None)
 folds={}
 for k in (3,5):
  edges=np.linspace(0,duration,k+1);folds[str(k)]=[scan(x,xb,y,yb,l,h,step=2,limit=100,min_lag=1) for l,h in zip(edges[:-1],edges[1:])]
  for f in folds[str(k)]:f.pop('curve',None)
 sensitivity=scan(x,xb,y,yb,0,duration,step=2,limit=100,min_lag=1,maxgap=5000);sensitivity.pop('curve',None)
 edges=np.linspace(0,duration,6);wide_folds=[scan(x,xb,y,yb,l,h,step=2,limit=500,min_lag=1) for l,h in zip(edges[:-1],edges[1:])]
 for f in wide_folds:f.pop('curve',None)
 return dict(status='ok',full=full,folds=folds,wide_all=wide,wide_fold5=wide_folds,gap5s=sensitivity)

def main():
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--prepare',action='store_true');a=p.parse_args();root=a.directory
 if a.prepare:
  series,bbos,quality=load_iex(records([Path('captures/ohio-iex-first-20261119/iex.bin.zst')]))
  (root/'iex-quality.json').write_text(json.dumps(quality,indent=2));np.savez_compressed(root/'iex-series.npz',**{k:np.array(v,dtype=float) for k,v in series.items()})
  for symbol,rows in bbos.items():(root/(symbol+'-iex-bbo.jsonl')).write_text(''.join(json.dumps(r)+'\n'for r in rows))
  print('IEX rows prepared',quality,flush=True);return
 data=np.load(root/'iex-series.npz');bounds=json.load(open(root/'window.json'));start,end=bounds['start_ns'],bounds['end_ns'];results=[]
 for m in json.load(open(root/'manifest.json')):
  symbol=m['symbol'];ticker='ETH' if symbol=='ETHUSDT' else symbol.removesuffix('BUSDT')
  if ticker not in data:continue
  raw=data[ticker];raw=raw[(raw[:,0]>=start)&(raw[:,0]<=end)];xmid=[((t-start)/1e6,(b+a)/2)for t,b,a in raw]
  ys=np.fromfile(root/'oracle'/(symbol+'-y.bin'),dtype='<f8').reshape(-1,2);ys=ys[(ys[:,0]>=start/1e6)&(ys[:,0]<=end/1e6)];source=compare(xmid,[(t-start/1e6,v)for t,v in ys],start,end)
  quotes=json.load(open(root/(ticker+'-pool-quotes.json')));out={}
  for side,column in [('bid',2),('ask',3),('mid',None)]:
   x=[((t-start)/1e6,(b+a)/2 if side=='mid' else b if side=='bid' else a)for t,b,a in raw];y=[]
   for q in quotes:
    if not start<=q[0]<=end:continue
    price=float('nan')if q[4]!='priced'else (float(q[column])/float(q[1]) if column else (float(q[2])+float(q[3]))/2/float(q[1]));y.append(((q[0]-start)/1e6,price))
   out[side]=compare(x,y,start,end)
  audit=json.load(open(root/(ticker+'-quote-clock-audit.json')))
  results.append(dict(ticker=ticker,pool=m['pool'],source_mid=source,pool_sides=out,iex_observations=len(raw),quote_audit=audit))
 result=dict(window=bounds,clock='Ohio application arrival; source calldata uses first relay receipt; pool clocks are state-update arrivals plus independent expiry ticks',positive_lag='IEX leads Metric',grid='0 and +/-1,3,...99,100 ms; 2 ms spacing; boundaries also scanned to +/-500 ms',scope='IEX venue BBO, not NBBO; descriptive HY, not profit; hypothetical fixed ~500 USDG quote size; no transaction submission',results=results)
 (root/'hy.json').write_text(json.dumps(result,indent=2)+'\n');lines=['# First IEX to Metric lead-lag','',result['scope'],'','Positive = IEX leads Metric. Source and executable-size pool quotes are separate.','', '| Ticker | IEX quotes | Source mid lag ms | Pool bid lag ms | Pool ask lag ms | Pool mid lag ms | Pool-mid 3 folds ms |','|---|---:|---:|---:|---:|---:|---|']
 def peak(r):return r.get('full',{}).get('peak_ms')
 for r in results:lines.append(f"| {r['ticker']} | {r['iex_observations']} | {peak(r['source_mid'])} | {peak(r['pool_sides']['bid'])} | {peak(r['pool_sides']['ask'])} | {peak(r['pool_sides']['mid'])} | {[peak(f if 'full'in f else {'full':f})for f in r['pool_sides']['mid'].get('folds',{}).get('3',[])]} |")
 lines+=['','Boundary peaks are censored estimates; see wider scans in hy.json. Fold sign changes, little price variation, or poor replay parity make a single peak unreliable. Compare matching instruments and account for token issuer/FX basis before trading. Quote replay assumes successful auxiliary calldata and does not imply executable fill acceptance. No profit claim follows from HY.']
 (root/'RESULTS.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True)
if __name__=='__main__':main()
