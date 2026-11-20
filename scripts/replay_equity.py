"""Read normalized spot-token BBO tapes; no network or RPC required."""
import argparse
import collections
import json
from tape import records

def main():
    p=argparse.ArgumentParser()
    p.add_argument('paths',nargs='+')
    p.add_argument('--ticker')
    p.add_argument('--venue')
    p.add_argument('--summary',action='store_true')
    p.add_argument('--include-late',action='store_true')
    a=p.parse_args();counts=collections.Counter();last={};events=collections.Counter();late=0
    for row in records(a.paths):
        events[row.get('kind')]+=1
        if row.get('kind')!='equity_bbo':continue
        if a.ticker and row['ticker']!=a.ticker:continue
        if a.venue and row['venue']!=a.venue:continue
        if row.get('is_late'):
            late+=1
            if not a.include_late:continue
        key=row['venue']+':'+row['instrument'];counts[key]+=1;last[key]=row['recv_ns']
        if not a.summary:print(json.dumps(row,separators=(',',':')))
    if a.summary:print(json.dumps(dict(counts=dict(counts),last_recv_ns=last,late_events=late,event_counts=dict(events)),indent=2))

if __name__=='__main__':main()
