"""Summarize an optimistic binary journal (a live incomplete tail is explicit)."""
import argparse
import collections
import json
from tape import records

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('tape');ap.add_argument('--output')
    a=ap.parse_args();counts=collections.Counter();causes=collections.Counter();symbols=collections.Counter()
    gaps=collections.Counter();delays=[];compute=[];checkpoints=[];tail_error=None;quotes=0
    try:
        for row in records([a.tape]):
            kind=row['kind'];counts[kind]+=1
            if kind=='optimistic_input':
                event=row['event']
                if event['kind'] in ('bbo','binance_bbo'):symbols[event['symbol']]+=1
            elif kind=='calldata_coverage_gap':gaps[row['reason']]+=1
            elif kind=='optimistic_checkpoint':
                checkpoints.append(dict(initial=row.get('initial'),generation=row.get('generation',0),
                    anchor=row['seed']['anchor']['number'],changed_pools=row.get('changed_pools',[]),
                    registry=bool(row.get('registry'))))
            elif kind=='amm_state_quote':
                causes[row['cause']]+=1;quotes+=int('bid' in row)
                if row.get('compute_ns') is not None:compute.append(row['compute_ns']/1e6)
                if row['cause']=='calldata' and row.get('available_ns') is not None and row['phase']=='optimistic_live':
                    delays.append((row['available_ns']-row['recv_ns'])/1e6)
    except ValueError as exc:tail_error=str(exc)
    def quantiles(v):
        v=sorted(v)
        return dict(count=len(v),**{label:v[int((len(v)-1)*q)] if v else None
            for label,q in [('p50',.5),('p90',.9),('p99',.99)]})
    result=dict(counts=dict(counts),quote_causes=dict(causes),quotes_with_bid_ask=quotes,
                binance_symbols=dict(symbols),checkpoints=checkpoints,
                coverage_gaps=gaps.most_common(15),quote_compute_ms=quantiles(compute),
                local_pipeline_wall_delay_ms=quantiles(delays),tail_error=tail_error,
                caveat='Optimistic V3 experiment; incomplete router coverage; not fill or profit evidence')
    text=json.dumps(result,indent=2)+'\n'
    if a.output:open(a.output,'w').write(text)
    else:print(text,end='')
if __name__=='__main__':main()
