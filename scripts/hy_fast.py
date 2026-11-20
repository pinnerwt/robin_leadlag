"""Vectorized equivalent of state_leadlag.hy_scan; preserves gap boundaries."""
import numpy as np
from state_leadlag import increments

def hy_scan(x,y,start,end,step=50,limit=5000):
 xr=increments(x,start,end,5000);yr=increments(y,start+limit,end-limit,15000)
 count=dict(binance_returns=len(xr),pool_returns=len(yr))
 norm=np.sqrt(sum(r*r for _,_,r in xr)*sum(r*r for _,_,r in yr))
 if not norm:return dict(status='insufficient_variation',**count)
 xa=np.asarray([a for a,b,r in xr]);xb=np.asarray([b for a,b,r in xr]);prefix=np.r_[0.,np.cumsum([r for a,b,r in xr])]
 # Zero contributions may be omitted only AFTER constructing the original intervals.
 nz=[(a,b,r) for a,b,r in yr if r!=0]
 ya=np.asarray([a for a,b,r in nz]);yb=np.asarray([b for a,b,r in nz]);dy=np.asarray([r for a,b,r in nz]);curve=[]
 for lag in range(-limit,limit+1,step):
  v=float(np.sum(dy*(prefix[np.searchsorted(xa,yb-lag,side='left')]-prefix[np.searchsorted(xb,ya-lag,side='right')]))/norm)
  curve.append([lag,v])
 peak=max(curve,key=lambda v:(v[1],-abs(v[0])))
 return dict(status='ok',**count,nonzero_pool_returns=len(nz),peak_ms=peak[0],peak_contrast=peak[1],zero_contrast=dict(curve)[0],curve=curve,peak_at_boundary=abs(peak[0])==limit)
