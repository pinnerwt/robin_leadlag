"""Offline chronological source-delay screening; all rankings retain pool address."""
import json,math
from pathlib import Path
import numpy as np
from tape import records
from ohio_20ms_backtest import load_bbos
from ohio_spot_hy import clean,scan
R=Path('reports/ohio-pool-ranking-20261119');segments=json.load(open(R/'segments.json'));manifest=json.load(open(R/'train/manifest.json'))
sources=[('ETH' if m['symbol']=='ETHUSDT' else m['symbol'].removesuffix('BUSDT'),m['symbol'],v) for m in manifest for v in ['binance','kraken','bybit']]
origins={m['symbol']:segments[0]['origin_ns'] for m in manifest}
streams,quality=load_bbos(records([Path('captures/ohio-pool-ranking-20261119/equity-window.bin.zst')]),sources,origins,segments[0]['start_utc_ns'],segments[-1]['end_utc_ns'])
(R/'bbo-quality.json').write_text(json.dumps(quality,indent=2));rows=[]
for segment in segments:
 d=Path(segment['directory']);start=segment['ready_ns'];end=segment['end_ns']
 for m in json.load(open(d/'manifest.json')):
  ticker='ETH' if m['symbol']=='ETHUSDT' else m['symbol'].removesuffix('BUSDT')
  events=[r for r in map(json.loads,open(d/(m['symbol']+'-events.jsonl'))) if r.get('mono_ns',0)<=end]
  (d/(m['symbol']+'-bounded-events.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in events))
  points=[]
  for r in events:
   if r['kind']!='oracle_candidate' or not start<=r['mono_ns']<=end:continue
   w=bytes.fromhex(r['word'].removeprefix('0x'));raw=int.from_bytes(w[:4],'big');price=(raw&((1<<27)-1))*2**(raw>>27)/1e8 if w[4:6]!=b'\xff\xff' else float('nan');points.append(((r['mono_ns']-start)/1e6,price))
  for venue in ['binance','kraken','bybit']:
   bb=[r for r in streams[(ticker,venue)] if start<=r['mono_ns']<=end];(d/(ticker+'-'+venue+'-bbo.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in bb))
   if d.name!='train' or len(bb)<10 or len(points)<10:continue
   x,xb=clean(np.array([((r['mono_ns']-start)/1e6,(float(r['bid'])+float(r['ask']))/2) for r in bb]));y,yb=clean(np.array(points));duration=(end-start)/1e6
   full=scan(x,xb,y,yb,0,duration,step=2,limit=500,min_lag=1);folds=[scan(x,xb,y,yb,l,h,step=2,limit=500,min_lag=1) for l,h in zip(np.linspace(0,duration,4)[:-1],np.linspace(0,duration,4)[1:])]
   for f in folds:f.pop('curve',None)
   full.pop('curve',None);rows.append(dict(ticker=ticker,symbol=m['symbol'],pool=m['pool'],venue=venue,full=full,folds=folds,minutes=duration/60000))
(R/'training-source-hy.json').write_text(json.dumps(dict(scope='compressed source mid, screening only; not executable bid/ask',positive='venue leads pool source',grid='0 and +/-1,3,...499,500 ms',results=rows),indent=2))
eligible=[r for r in rows if r['full'].get('status')=='ok' and r['full']['peak_ms']>0 and not r['full']['boundary']]
eligible.sort(key=lambda r:(sum(f.get('peak_ms',0)>0 for f in r['folds']),r['full']['peak_ms']),reverse=True)
selected=[];seen=set()
for r in eligible:
 if r['pool'] in seen:continue
 seen.add(r['pool']);selected.append(r)
 if len(selected)==5:break
(R/'selected-pools.json').write_text(json.dumps(selected,indent=2));print('selected',[(r['ticker'],r['venue'],r['full']['peak_ms'],[f.get('peak_ms') for f in r['folds']]) for r in selected],flush=True)
