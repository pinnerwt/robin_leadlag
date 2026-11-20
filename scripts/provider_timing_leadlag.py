"""Separate sequencer-source arrival from log-validated pool quote availability."""
import argparse,json,numpy as np
from hy_fast import hy_scan
import state_leadlag
state_leadlag.hy_scan=hy_scan
p=argparse.ArgumentParser();p.add_argument('quotes');p.add_argument('feeds');p.add_argument('--output',required=True);a=p.parse_args()
x=[];qtime=[]
for line in open(a.quotes):
 r=json.loads(line)
 if r['kind']=='bbo':x.append((r['mono_ns']/1e6,(float(r['bid'])+float(r['ask']))/2))
 if r['kind']=='state_quote':qtime.append(r['available_mono_ns']/1e6)
feeds=[json.loads(l) for l in open(a.feeds)];start=max(min(t for t,p in x),min(qtime));end=min(max(t for t,p in x),max(qtime))
result={'scope':'accepted provider source prices, not size-dependent pool quotes','common_support_ms':[start,end],'positive_lag':'Binance leads provider source arrival','results':{}}
delays=[(r['log_mono_ns']-r['mono_ns'])/1e6 for r in feeds if start<=r['mono_ns']/1e6<=end]
result['feed_to_log_ms']={k:float(np.quantile(delays,q)) for k,q in [('p50',.5),('p90',.9),('p99',.99),('max',1)]};result['feed_to_log_samples']=len(delays)
for side in ('bid','ask','mid'):
 y=[(r['mono_ns']/1e6,r[side]) for r in feeds]
 result['results'][side]={'full':hy_scan(x,y,start,end,50,5000),'walk_forward':{str(k):state_leadlag.walk_forward(x,y,start,end,k,50,5000) for k in (3,5,10)}}
json.dump(result,open(a.output,'w'),indent=2)
print(json.dumps({'delays':result['feed_to_log_ms'],'peaks':{s:r['full']['peak_ms'] for s,r in result['results'].items()}},indent=2))
