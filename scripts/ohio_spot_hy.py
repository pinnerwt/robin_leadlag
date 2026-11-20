"""Receipt-time HY comparisons of spot BBO; oracle source is separately labeled."""
import argparse
import collections
import datetime
import itertools
import json
import math
from pathlib import Path
import numpy as np
from tape import records


def rfc_ns(value):
    whole,fraction=(value[:-1].split('.',1)+[''])[:2] if '.' in value else (value[:-1],'')
    base=datetime.datetime.strptime(whole,'%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return int(base.timestamp())*10**9+int(fraction.ljust(9,'0'))


def load_equities(paths,start_ns,end_ns):
    series=collections.defaultdict(list);quality=collections.Counter();latest_source={};links={};catalog={}
    def boundary(venue,t):
        for symbol in catalog.get(venue,[]):
            for side in ('mid','bid','ask'):series[(venue,symbol,side)].append((t,float('nan')))
    for path in paths:
        links={}
        for r in records([path]):
            kind=r.get('kind');recv=r.get('recv_ns',0);t=(recv-start_ns)/1e6
            if kind=='equity_session':
                for feed in r['config']['feeds']:
                    venue=feed['venue'];catalog[venue]={v['ticker'] for v in feed['instruments'].values()};boundary(venue,t)
            elif kind in ('connected','ready','gap'):
                link=r['link'];venue=r['venue'];links[link]=(venue,kind=='ready')
                if kind=='gap':
                    quality[venue+'_link_gaps']+=1
                    if not any(v==venue and ready for v,ready in links.values()):
                        boundary(venue,t);quality[venue+'_all_links_down']+=1
            elif kind=='rotation_complete':
                links.pop(r['old_link'],None);quality['warm_rotations']+=1
            elif kind=='equity_capture_end':
                for venue in catalog:boundary(venue,t)
            if kind!='equity_bbo' or not start_ns<=recv<=end_ns:continue
            v,s=r['venue'],r['ticker'];key=(v,s)
            if r.get('is_late'):
                quality[v+'_late_sequence']+=1;continue
            if v=='kraken':
                stamp=rfc_ns(r['exchange_timestamp'])
                if stamp<latest_source.get(key,0):
                    quality['kraken_stale_source']+=1;continue
                # Reconnect snapshots are observations, not freshly published moves.
                if r.get('message_type')=='snapshot' and key in latest_source:
                    quality['kraken_repeat_snapshot']+=1;continue
                latest_source[key]=stamp
            b,a=float(r['bid']),float(r['ask']);valid=math.isfinite(b) and math.isfinite(a) and b>0 and a>=b
            if not valid:quality[v+'_invalid_bbo']+=1
            for side,p in [('bid',b),('ask',a),('mid',(a+b)/2)]:series[(v,s,side)].append((t,p if valid else float('nan')))
            quality[v+'_quotes']+=1
    return {k:np.asarray(v,dtype=float) for k,v in series.items()},dict(quality)


def clean(points):
    points=points[np.argsort(points[:,0],kind='stable')]
    starts=np.r_[0,np.flatnonzero(np.diff(points[:,0]))+1];ends=np.r_[starts[1:]-1,len(points)-1]
    bad=np.logical_or.reduceat(~np.isfinite(points[:,1])|(points[:,1]<=0),starts)
    return points[ends],bad


def increments(points,bad,start,end,maxgap):
    lo=np.searchsorted(points[:,0],start);hi=np.searchsorted(points[:,0],end,side='right');p=points[lo:hi];invalid=bad[lo:hi]
    if len(p)<2:return np.empty((0,3))
    good=(~invalid[1:])&np.isfinite(p[:-1,1])&(p[:-1,1]>0)&(np.diff(p[:,0])>0)&(np.diff(p[:,0])<=maxgap)
    i=np.flatnonzero(good)
    return np.column_stack((p[i,0],p[i+1,0],np.log(p[i+1,1]/p[i,1])))


def scan(x,xb,y,yb,start,end,step=50,limit=2000,maxgap=15000,min_lag=0):
    if end-start<=2*limit:return dict(status='insufficient_duration')
    xr=increments(x,xb,start,end,maxgap);yr=increments(y,yb,start+limit,end-limit,maxgap)
    n=float(np.sqrt(np.sum(xr[:,2]**2)*np.sum(yr[:,2]**2)))
    out=dict(x_returns=len(xr),y_returns=len(yr),x_nonzero=int(np.count_nonzero(xr[:,2])),y_nonzero=int(np.count_nonzero(yr[:,2])))
    if n==0:return dict(out,status='insufficient_variation')
    active=yr[yr[:,2]!=0];prefix=np.r_[0.,np.cumsum(xr[:,2])];curve=[]
    positive=list(range(min_lag,limit+1,step))
    lags=sorted({0,-limit,limit,*positive,*(-v for v in positive)})
    for lag in lags:
        left=np.searchsorted(xr[:,1],active[:,0]-lag,side='right');right=np.searchsorted(xr[:,0],active[:,1]-lag,side='left')
        value=float(np.sum(active[:,2]*(prefix[right]-prefix[left]))/n)
        curve.append([lag,value])
    peak=max(curve,key=lambda p:(p[1],-abs(p[0])))
    return dict(out,status='ok',peak_ms=peak[0],peak_contrast=peak[1],zero_contrast=dict(curve)[0],delta_vs_zero=peak[1]-dict(curve)[0],boundary=abs(peak[0])==limit,curve=curve)


def analyze(series,limit=100,step=2,min_lag=1):
    results=[];keys=set(series)
    for ticker in sorted({s for v,s,side in keys}):
        venues=sorted({v for v,s,side in keys if s==ticker and side=='mid' and len(series[(v,s,side)])})
        for xname,yname in itertools.combinations(venues,2):
            for side in ('mid','bid','ask'):
                if (xname,ticker,side) not in keys or (yname,ticker,side) not in keys:continue
                x,xb=clean(series[(xname,ticker,side)]);y,yb=clean(series[(yname,ticker,side)])
                valid_x=x[np.isfinite(x[:,1])&(x[:,1]>0)];valid_y=y[np.isfinite(y[:,1])&(y[:,1]>0)]
                if not len(valid_x) or not len(valid_y):continue
                start=max(valid_x[0,0],valid_y[0,0]);end=min(valid_x[-1,0],valid_y[-1,0])
                # Restrict first/last support; long quiet observations still have a capped return interval.
                full=scan(x,xb,y,yb,start,end,step=step,limit=limit,min_lag=min_lag)
                folds={}
                for k in (3,5,10):
                    edges=np.linspace(start,end,k+1)
                    folds[str(k)]=[scan(x,xb,y,yb,l,h,step=step,limit=limit,min_lag=min_lag) for l,h in zip(edges[:-1],edges[1:])]
                    for f in folds[str(k)]:f.pop('curve',None)
                peaks=[f['peak_ms'] for f in folds['5'] if f.get('status')=='ok']
                results.append(dict(ticker=ticker,x=xname,y=yname,side=side,support_minutes=(end-start)/60000,full=full,folds=folds,fold5_peaks_ms=peaks,gap5s_sensitivity=scan(x,xb,y,yb,start,end,step=step,limit=limit,maxgap=5000,min_lag=min_lag)))
    return results


def main():
    p=argparse.ArgumentParser();p.add_argument('paths',nargs='+');p.add_argument('--start-ns',type=int,required=True);p.add_argument('--end-ns',type=int,required=True);p.add_argument('--oracle-directory');p.add_argument('--output',required=True);a=p.parse_args()
    series,quality=load_equities(a.paths,a.start_ns,a.end_ns)
    if a.oracle_directory:
        root=Path(a.oracle_directory)
        for m in json.load(open(root/'manifest.json')):
            symbol=m['symbol'];ticker='ETH' if symbol=='ETHUSDT' else symbol.removesuffix('BUSDT')
            points=np.fromfile(root/(symbol+'-y.bin'),dtype='<f8').reshape(-1,2);points[:,0]-=a.start_ns/1e6
            points=points[(points[:,0]>=0)&(points[:,0]<=(a.end_ns-a.start_ns)/1e6)]
            if len(points):series[('robinhood_source',ticker,'mid')]=points
        quality['oracle_extraction']=json.load(open(root/'extraction.json'))
    result=dict(scope='Ohio first-arrival spot BBO; optimistic calldata oracle source is separately labeled, not executable pool bid/ask',positive_lag='X leads Y by peak_ms; negative means Y leads X',step_ms=2,min_lag_ms=1,limit_ms=100,lag_grid_ms=sorted({0,-100,100,*range(1,100,2),*range(-99,0,2)}),max_return_gap_ms=15000,clock='actual Ohio receipt time; no synthetic route offsets',contrast='normalized Hayashi-Yoshida covariance, not bounded Pearson correlation or profit',folds='chronological independent 3/5/10 partitions, descriptive stability',start_ns=a.start_ns,end_ns=a.end_ns,quality=quality,results=analyze(series))
    output=Path(a.output);output.mkdir(parents=True,exist_ok=True);(output/'hy.json').write_text(json.dumps(result,indent=2)+'\n')
    rows=['# Ohio spot lead-lag','',result['scope'],'','Positive lag: X leads Y. Grid ±1,3,...99 ms plus 0 and ±100 ms. HY contrast is not profit.','', '| Ticker | X | Y | Minutes | Peak ms | HY | Delta vs zero | Five chronological fold peaks (ms) |','|---|---|---|---:|---:|---:|---:|---|']
    for r in result['results']:
        if r['side']!='mid' or r['full'].get('status')!='ok':continue
        f=r['full'];rows.append(f"| {r['ticker']} | {r['x']} | {r['y']} | {r['support_minutes']:.1f} | {f['peak_ms']} | {f['peak_contrast']:.4f} | {f['delta_vs_zero']:.4f} | {r['fold5_peaks_ms']} |")
    (output/'RESULTS.md').write_text('\n'.join(rows)+'\n')
    # Preserve event arrays for charts/reproducible sensitivity checks without rereading tapes.
    np.savez_compressed(output/'series.npz',**{'__'.join(k):v for k,v in series.items()})
    print('\n'.join(rows))

if __name__=='__main__':main()
