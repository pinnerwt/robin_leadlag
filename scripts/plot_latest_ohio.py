"""Static descriptive HY figure; no resampling is applied to the estimator."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();r=a.directory
rows=json.load(open(r/'manifest.json'));selected=[m for m in rows if m['ticker']in ['ETH','SPCX','META','NVDA','AAPL']];fig,axes=plt.subplots(3,2,figsize=(12,10),constrained_layout=True)
for ax,m in zip(axes.flat,selected):
 h=next(x for x in json.load(open(r/(m['symbol']+'-hy.json'))) if x['venue']=='binance')
 for side,color in [('bid','#16816a'),('ask','#cf702b')]:
  s=h['sides'][side];curve=s.get('full',{}).get('curve',[])
  if curve:ax.plot([v[0]for v in curve],[v[1]for v in curve],label=side,color=color)
 ax.axvline(0,color='gray',ls='--',lw=.8);ax.axvline(20,color='#7663aa',ls=':',lw=1);ax.set_title(m['ticker']+' '+m['pool'][:10]);ax.set_xlim(-100,100);ax.set_xlabel('Lag ms (+ = Binance leads pool)');ax.set_ylabel('Normalized HY contrast')
 if ax.get_legend_handles_labels()[0]:ax.legend()
 else:ax.text(.5,.5,'Two-sided ~500 USDG quote unavailable',ha='center',transform=ax.transAxes)
fig.suptitle('Ohio receipts: Nov 19 22:00 to Nov 20 01:35 UTC\nFixed ~500 USDG quotes; dotted line = assumed 20 ms execution; descriptive, not PnL')
fig.savefig(r/'binance-pool-hy.png',dpi=160)
# One descriptive zoom, selected solely by the largest adjacent Binance mid move
# with <=100 ms between observations in the held-out half. No timestamp shifts.
import math,bisect
w=json.load(open(r/'window.json'));bb=[];previous=None;best=None
for line in open(r/'ETH-binance-bbo.jsonl'):
 x=json.loads(line)
 if x.get('invalid'):previous=None;continue
 t=x['recv_ns'];bid=float(x['bid']);ask=float(x['ask']);mid=(bid+ask)/2
 if previous is not None and w['split_ns']<=t and 0<t-previous[0]<=100_000_000:
  magnitude=abs(math.log(mid/previous[1]))
  if best is None or magnitude>best[0]:best=(magnitude,t)
 previous=(t,mid)
 if not bb or (bid,ask)!=(bb[-1][1],bb[-1][2]):bb.append((t,bid,ask))
if best:
 t0=best[1];lo=t0-500_000_000;hi=t0+1_500_000_000;times=[x[0]for x in bb];b=bb[max(0,bisect.bisect_left(times,lo)-1):bisect.bisect_right(times,hi)]
 b.append((hi,b[-1][1],b[-1][2]))
 m=next(m for m in rows if m['pool'].startswith('0x1e8fc442'));q=json.load(open(r/(m['symbol']+'-quotes.json')));qt=[x[0]for x in q];q=q[max(0,bisect.bisect_left(qt,lo)-1):bisect.bisect_right(qt,hi)]
 fig,axes=plt.subplots(2,1,figsize=(11,6),sharex=True,constrained_layout=True)
 for ax,side,bi,qi,color in zip(axes,['bid','ask'],[1,2],[2,3],['#16816a','#cf702b']):
  ax.step([(x[0]-t0)/1e6 for x in b],[x[bi]for x in b],where='post',label='Binance '+side,color='black',lw=1)
  ax.step([(x[0]-t0)/1e6 for x in q],[float(x[qi])/float(x[1])if x[4]=='priced'else float('nan')for x in q],where='post',label='Metric '+side+' (~500 USDG)',color=color,lw=1.5)
  ax.axvline(0,color='gray',ls=':');ax.set_ylabel('Price / ETH');ax.legend();ax.set_xlim(-500,1500)
 axes[-1].set_xlabel('Ohio receipt time relative to selected Binance move (ms)')
 fig.suptitle('ETH price replay: corrected writer binding, unshifted arrival clocks\nDescriptive zoom; pool fees/size impact included; USDG = USDT assumed')
 fig.savefig(r/'eth-price-replay.png',dpi=160)
 (r/'price-plot-selection.json').write_text(json.dumps({'selection':'Largest adjacent Binance mid move in test half with <=100 ms interval, descriptive only','move_recv_ns':t0,'move_bps':best[0]*10000,'window_ns':[lo,hi]},indent=2))
