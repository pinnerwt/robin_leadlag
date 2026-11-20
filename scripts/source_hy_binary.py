"""Offline HY of optimistic oracle-source mid; not executable pool bid/ask."""
import argparse,json
from pathlib import Path
import numpy as np

def load(path):
 a=np.fromfile(path,dtype='<f8').reshape(-1,2);a=a[np.argsort(a[:,0],kind='stable')]
 starts=np.r_[0,np.flatnonzero(np.diff(a[:,0]))+1];ends=np.r_[starts[1:]-1,len(a)-1]
 invalid=~np.isfinite(a[:,1])|(a[:,1]<=0)
 return a[ends],np.logical_or.reduceat(invalid,starts)

def increments(points,invalid,start,end,maxgap):
 lo=np.searchsorted(points[:,0],start);hi=np.searchsorted(points[:,0],end,side='right');a=points[lo:hi];bad=invalid[lo:hi]
 if len(a)<2:return np.empty((0,3))
 good=(~bad[1:])&np.isfinite(a[:-1,1])&(a[:-1,1]>0)&(np.diff(a[:,0])<=maxgap)
 idx=np.flatnonzero(good);return np.column_stack((a[idx,0],a[idx+1,0],np.log(a[idx+1,1]/a[idx,1])))

def scan(x,xb,y,yb,start,end):
 xr=increments(x,xb,start,end,5000);yr=increments(y,yb,start+5000,end-5000,15000)
 norm=np.sqrt(np.sum(xr[:,2]**2)*np.sum(yr[:,2]**2));out=dict(binance_returns=len(xr),provider_returns=len(yr))
 if norm==0:return dict(out,status='insufficient_variation')
 yr=yr[yr[:,2]!=0];prefix=np.r_[0.,np.cumsum(xr[:,2])];curve=[]
 for lag in range(-5000,5001,50):
  left=np.searchsorted(xr[:,1],yr[:,0]-lag,side='right');right=np.searchsorted(xr[:,0],yr[:,1]-lag,side='left')
  curve.append([lag,float(np.sum(yr[:,2]*(prefix[right]-prefix[left]))/norm)])
 peak=max(curve,key=lambda p:(p[1],-abs(p[0])))
 return dict(out,status='ok',nonzero_provider_returns=len(yr),peak_ms=peak[0],peak_contrast=peak[1],zero_contrast=dict(curve)[0],boundary=abs(peak[0])==5000,curve=curve)

def main():
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();manifest=json.load(open(a.directory/'manifest.json'))
 result=dict(scope='optimistic source mid at Nitro relay arrival versus Binance mid at Taiwan receipt; not executable pool quotes',step_ms=50,positive_lag='Binance leads source',folds='independent chronological partitions; descriptive stability, not heldout strategy selection',ohio_translation='For constant Binance +100ms and chain -175ms offsets, subtract 275ms from Taiwan lag. Execution delay is separate.',results={})
 for m in manifest:
  symbol=m['symbol'];x,xb=load(a.directory/(symbol+'-x.bin'));y,yb=load(a.directory/(symbol+'-y.bin'));start=max(x[0,0],y[0,0]);end=min(x[-1,0],y[-1,0]);r=dict(full=scan(x,xb,y,yb,start,end),folds={})
  for k in (3,5,10):
   edges=np.linspace(start,end,k+1);r['folds'][str(k)]=[scan(x,xb,y,yb,l,h) for l,h in zip(edges[:-1],edges[1:])]
  result['results'][symbol]=r;(a.directory/'hy.json').write_text(json.dumps(result,indent=2)+'\n');print(symbol,r['full'].get('peak_ms'),r['full'].get('peak_contrast'),[f.get('peak_ms')for f in r['folds']['5']],flush=True)
if __name__=='__main__':main()
