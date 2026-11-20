"""Research HY for explicitly approximate quotes; never relabels them executable."""
import argparse,json,collections,math
import state_leadlag
try:
 from hy_fast import hy_scan
 state_leadlag.hy_scan=hy_scan
except ImportError:
 from state_leadlag import hy_scan
from state_leadlag import walk_forward
p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output',required=True);a=p.parse_args()
x=[];ys={s:[] for s in ('bid','ask','mid')};quality=collections.Counter();gaps=[]
for line in open(a.input):
 r=json.loads(line)
 if r['kind']=='bbo' and r['symbol']=='SPCXBUSDT':
  bid=float(r['bid']);ask=float(r['ask'])
  x.append((r['mono_ns']/1e6,(bid+ask)/2 if 0<bid<=ask else None))
 elif r['kind']=='gap':gaps.append(r['mono_ns']/1e6)
 elif r['kind']=='state_quote':
  good=r.get('model_priced') is True and 0<float(r['bid'])<=float(r['ask']);quality['priced' if good else 'unavailable']+=1
  for side in ys:
   v=((float(r['bid'])+float(r['ask']))/2 if side=='mid' else float(r[side])) if good else None
   ys[side].append((r['available_mono_ns']/1e6,v))
for t in gaps:
 x.append((t,None))
 for y in ys.values():y.append((t,None))
start=max(min(t for t,_ in x),min(t for t,_ in ys['mid']));end=min(max(t for t,_ in x),max(t for t,_ in ys['mid']))
result={'status':'approximate_state_research','positive_lag':'Binance leads observed pool quote arrival','input':a.input,'step_ms':50,'quality':quality,'binance_rows':len(x),'duration_ms':end-start,'results':{},'limitations':['Log-validated availability clock, not pure Nitro provider arrival','Source-only model ignores provider rejection/expiry and freezes some dependencies','No unavailable quotes carried forward across gaps','HY normalized covariance is not Pearson correlation or a profit estimate']}
for side,y in ys.items():
 full=hy_scan(x,y,start,end,50,5000)
 result['results'][side]={'full':full,'walk_forward':{str(k):walk_forward(x,y,start,end,k,50,5000) for k in (3,5,10)},'broad':hy_scan(x,y,start,end,1000,120000)}
 print(side,full.get('peak_ms'),full.get('peak_contrast'),flush=True)
json.dump(result,open(a.output,'w'),indent=2)
try:
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(2,1,figsize=(11,7),constrained_layout=True)
 for side,r in result['results'].items():
  c=r['full'].get('curve',[])
  if c:axes[0].plot([t for t,v in c],[v for t,v in c],label=side)
  c=r['broad'].get('curve',[])
  if c:axes[1].plot([t/1000 for t,v in c],[v for t,v in c],label=side)
 for ax in axes:ax.axvline(0,color='gray',lw=.7);ax.legend();ax.set_ylabel('Normalized HY covariance')
 axes[0].set_xlabel('Lag (ms), positive = Binance leads observed quote');axes[1].set_xlabel('Lag (seconds), broad diagnostic')
 fig.suptitle('SPCX approximate state quotes vs Binance — arrival-time research only')
 fig.savefig(a.output.replace('.json','.png'),dpi=160)
except ImportError:pass
