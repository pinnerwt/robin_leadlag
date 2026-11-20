"""Compact receipt-time HY result visualization; no executable-profit claims."""
import argparse,json,os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/robin-leadlag-matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();data=json.load(open(a.directory/'hy.json'))
 rows=[r for r in data['results'] if r['side']=='mid' and r['full'].get('status')=='ok']
 tickers=sorted({r['ticker'] for r in rows});pairs=sorted({(r['x'],r['y']) for r in rows});table={(r['ticker'],(r['x'],r['y'])):r for r in rows}
 values=np.full((len(tickers),len(pairs)),np.nan)
 for i,t in enumerate(tickers):
  for j,pair in enumerate(pairs):
   if (t,pair) in table:values[i,j]=table[t,pair]['full']['peak_ms']
 fig,ax=plt.subplots(figsize=(max(9,len(pairs)*1.8),max(5,len(tickers)*.5)))
 image=ax.imshow(values,cmap='RdBu_r',vmin=-data['limit_ms'],vmax=data['limit_ms'],aspect='auto')
 ax.set_xticks(range(len(pairs)),[x+' →\n'+y.replace('robinhood_source','RH source') for x,y in pairs],fontsize=9)
 ax.set_yticks(range(len(tickers)),tickers)
 for i,t in enumerate(tickers):
  for j,pair in enumerate(pairs):
   r=table.get((t,pair))
   if not r:ax.text(j,i,'—',ha='center',va='center',color='gray');continue
   f=r['full'];peaks=r['fold5_peaks_ms'];lag=f['peak_ms']
   stable=sum(np.sign(v)==np.sign(lag) for v in peaks)
   ax.text(j,i,f"{lag:+d}\n{stable}/{len(peaks)} folds",ha='center',va='center',fontsize=8,color='white' if abs(lag)>data['limit_ms']*.65 else 'black')
 ax.set_title(f"Ohio receipt-time lead–lag: HY peak (ms), {data['step_ms']} ms grid\nPositive = left source leads right; fold count = same peak sign",pad=16)
 fig.colorbar(image,ax=ax,label=f"HY peak lag (ms), scan ±{data['limit_ms']} ms")
 fig.text(.5,.01,'RH source = optimistic calldata oracle mid, NOT executable pool bid/ask. Short-window descriptive evidence.',ha='center',fontsize=8)
 fig.tight_layout(rect=(0,.04,1,1));fig.savefig(a.directory/'leadlag-heatmap.png',dpi=160);plt.close(fig)
 # Full profiles for the primary Binance-to-source comparison reveal broad/weak peaks.
 oracle=[r for r in rows if r['x']=='binance' and r['y']=='robinhood_source']
 if oracle:
  fig,axes=plt.subplots(int(np.ceil(len(oracle)/3)),3,figsize=(12,3*int(np.ceil(len(oracle)/3))),squeeze=False)
  for ax,r in zip(axes.flat,oracle):
   curve=np.asarray(r['full']['curve']);ax.plot(curve[:,0],curve[:,1],lw=1.4);ax.axvline(0,color='gray',lw=.8);ax.axvline(r['full']['peak_ms'],color='orange',ls='--');ax.set_title(r['ticker']);ax.set_xlabel('Lag ms; positive Binance leads');ax.set_ylabel('HY contrast');ax.grid(alpha=.2)
  for ax in list(axes.flat)[len(oracle):]:ax.axis('off')
  fig.suptitle('Binance spot vs optimistic Robinhood source: full HY profiles');fig.tight_layout();fig.savefig(a.directory/'binance-source-hy.png',dpi=160);plt.close(fig)
if __name__=='__main__':main()
