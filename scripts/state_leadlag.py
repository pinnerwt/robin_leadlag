"""HY analysis of verified state quotes. Never substitutes swaps or oracle mids.

Input: JSONL bbo rows and state_quote rows on one session's monotonic clock.
state_quote requires symbol, pool, size_tokens, bid, ask, available_mono_ns,
state_complete=true, executable=true. Invalid quote rows break return intervals.
"""
import argparse
import bisect
from collections import defaultdict
import json
from itertools import groupby
import math
import sys


def increments(points, start, end, max_gap):
    result=[];previous=None
    for t, group in groupby(sorted(points,key=lambda point:point[0]), key=lambda point:point[0]):
        values=[price for _,price in group]
        p=values[-1]
        if not start<=t<=end:continue
        # Several updates can become available together. Observe the final state,
        # never lose the last move or invent an interval of zero duration.
        if any(value is None or not math.isfinite(value) or value<=0 for value in values):
            previous=None
        if p is None or not math.isfinite(p) or p<=0:continue
        if previous:
            a,q=previous
            if 0<t-a<=max_gap:result.append((a,t,math.log(p/q)))
        previous=(t,p)
    return result


def hy_scan(x,y,start,end,step=50,limit=5000):
    # Common support for every candidate lag. Y is shifted backwards for positive lag.
    xr=increments(x,start,end,5000)
    yr=increments(y,start+limit,end-limit,15000)
    starts=[a for a,_,_ in xr];ends=[b for _,b,_ in xr]
    prefix=[0.]
    for _,_,r in xr:prefix.append(prefix[-1]+r)
    norm=math.sqrt(sum(r*r for _,_,r in xr)*sum(r*r for _,_,r in yr))
    if not norm:return dict(status='insufficient_variation',binance_returns=len(xr),pool_returns=len(yr))
    curve=[]
    for lag in range(-limit,limit+1,step):
        value=sum(r*(prefix[bisect.bisect_left(starts,b-lag)]-prefix[bisect.bisect_right(ends,a-lag)]) for a,b,r in yr)/norm
        curve.append([lag,value])
    peak=max(curve,key=lambda v:(v[1],-abs(v[0])))
    return dict(status='ok',binance_returns=len(xr),pool_returns=len(yr),peak_ms=peak[0],
                peak_contrast=peak[1],zero_contrast=next(v for t,v in curve if t==0),curve=curve,
                peak_at_boundary=abs(peak[0])==limit)


def walk_forward(x,y,start,end,k,step,limit):
    width=(end-start)/k;results=[]
    for fold in range(1,k):
        cut=start+width*fold
        train=hy_scan(x,y,start,cut,step,limit)
        test=hy_scan(x,y,cut,min(end,cut+width),step,limit)
        row=dict(fold=fold+1,train_end_ms=cut,test_end_ms=min(end,cut+width))
        if train['status']=='ok' and test['status']=='ok':
            lag=train['peak_ms'];score=dict(test['curve'])[lag]
            row.update(selected_lag_ms=lag,heldout_contrast=score,delta_vs_zero=score-test['zero_contrast'])
        else:row['status']='insufficient_variation'
        results.append(row)
    return results


def analyze(rows, x_ms=None,y_ms=None,tokyo_taiwan_ms=25,step=50,limit=5000):
    if (x_ms is None)!=(y_ms is None):raise ValueError('X and Y must be supplied together')
    if step<=0 or limit<=0 or limit%step:raise ValueError('limit must be a positive multiple of step')
    shift_b=0 if x_ms is None else x_ms-tokyo_taiwan_ms
    shift_r=0 if y_ms is None else -y_ms
    if x_ms is not None and min(x_ms,y_ms,tokyo_taiwan_ms)<0:raise ValueError('negative one-way latency')
    bbo=defaultdict(list);quotes=defaultdict(list);invalid=0;boundaries=[];sessions=0
    for row in rows:
        kind=row['kind']
        if kind=='session':
            sessions+=1
            if sessions>1:raise ValueError('analyze sessions separately: monotonic origins differ')
        if kind=='gap':boundaries.append(row['mono_ns']/1e6);continue
        if kind=='bbo':
            t=row['mono_ns']/1e6+shift_b
            bbo[row['symbol']].append((t,(float(row['bid'])+float(row['ask']))/2))
        if kind=='state_quote':
            # Read availability, not earlier triggering feed arrival or retroactive block time.
            t=row['available_mono_ns']/1e6+shift_r
            valid=row.get('state_complete') is True and row.get('executable') is True
            invalid+=not valid
            for side in ('bid','ask','mid'):
                price=(float(row['bid'])+float(row['ask']))/2 if valid and side=='mid' else float(row[side]) if valid else None
                quotes[(row['symbol'],row['pool'],str(row['size_tokens']),side)].append((t,price))
    results=[]
    for (symbol,pool,size,side),y in quotes.items():
        x=list(bbo.get(symbol,[]))
        if not x:continue
        x.extend((t+shift_b,None) for t in boundaries)
        y.extend((t+shift_r,None) for t in boundaries)
        start=max(min(t for t,_ in x),min(t for t,_ in y))
        end=min(max(t for t,_ in x),max(t for t,_ in y))
        results.append(dict(symbol=symbol,pool=pool,size_tokens=size,side=side,
                            full=hy_scan(x,y,start,end,step,limit),
                            walk_forward={str(k):walk_forward(x,y,start,end,k,step,limit) for k in (3,5,10)}))
    return dict(status='ok' if any(r['full']['status']=='ok' for r in results) else 'no_verified_state_quotes',
                positive_lag='Binance leads Robinhood',contrast='normalized HY covariance, not bounded Pearson correlation or profit',
                timing=dict(mode='local' if x_ms is None else 'hypothetical_route',binance_shift_ms=shift_b,robinhood_shift_ms=shift_r,
                            route_assumption='Binance via Tokyo and Robinhood via Ohio; constant delays, not measured jitter'),
                invalid_quote_rows=invalid,binance_symbols=sorted(bbo),results=results)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tokyo-ohio-ms',type=float);p.add_argument('--ohio-taiwan-ms',type=float)
    p.add_argument('--tokyo-taiwan-ms',type=float,default=25)
    p.add_argument('--step-ms',type=int,default=50);p.add_argument('--limit-ms',type=int,default=5000)
    a=p.parse_args()
    print(json.dumps(analyze((json.loads(line) for line in sys.stdin),a.tokyo_ohio_ms,a.ohio_taiwan_ms,a.tokyo_taiwan_ms,a.step_ms,a.limit_ms),indent=2))
