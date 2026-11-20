"""Later-window actual fixed-size pool quote HY; separate from backtest fills."""
import json,math
from pathlib import Path
from iex_pool_hy import compare
R=Path('reports/ohio-latest-20261119T2103Z');w=json.load(open(R/'window.json'));start=w['split_ns'];end=w['end_ns'];out=[]
for m in json.load(open(R/'manifest.json')):
 if m['symbol']=='ETHUSDT':continue
 t=m['symbol'].removesuffix('BUSDT');b=[r for r in map(json.loads,open(R/(t+'-iex-bbo.jsonl')))if start<=r['recv_ns']<=end];q=[r for r in json.load(open(R/(t+'-pool-quotes.json')))if start<=r[0]<=end];sides={}
 for side,i in [('bid',2),('ask',3),('mid',None)]:
  x=[((r['recv_ns']-start)/1e6,float('nan')if r.get('invalid')else(float(r['bid'])+float(r['ask']))/2 if side=='mid'else float(r[side]))for r in b]
  y=[((r[0]-start)/1e6,float('nan')if r[4]!='priced'else (float(r[2])+float(r[3]))/2/float(r[1])if i is None else float(r[i])/float(r[1]))for r in q]
  sides[side]=compare(x,y,start,end)
 out.append(dict(ticker=t,pool=m['pool'],fixed_quantity=q[0][1]if q else None,valid_quote_observations=sum(r[4]=='priced'for r in q),unavailable_observations=sum(r[4]!='priced'for r in q),sides=sides));print(t,{s:r.get('wide_all',{}).get('peak_ms')for s,r in sides.items()},flush=True)
(R/'pool-hy-test.json').write_text(json.dumps(dict(positive='IEX leads quoted pool side',window_ns=[start,end],size='Fixed approximately 500 USDG at initial IEX ask; not changing with reference ticks',results=out),indent=2))
