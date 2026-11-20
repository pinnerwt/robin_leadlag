"""Report size-matched predictions made before observed depth reconciliation."""
import argparse,json,collections
p=argparse.ArgumentParser();p.add_argument('input');a=p.parse_args()
rows=[];fails=[];quotes=collections.Counter()
for line in open(a.input):
 r=json.loads(line)
 if r['kind']=='swap_prediction':rows.append(r)
 elif r['kind']=='swap_failure':fails.append(r)
 elif r['kind']=='state_quote':quotes['priced' if r.get('model_priced') else 'unavailable']+=1

def quantile(v,q):
 v=sorted(v)
 if not v:return None
 n=(len(v)-1)*q;i=int(n);return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(n-i)
sides={}
for side in ['buy','sell']:
 rs=[r for r in rows if r['side']==side];errors=[abs(r['price_error_bps']) for r in rs]
 sides[side]={'n':len(rs),'token_exact':sum(r['token_delta_exact'] for r in rs),'bin_exact_before_reconciliation':sum(r['bin_logs_exact'] for r in rs),'abs_price_error_bps':{k:quantile(errors,q) for k,q in [('p50',.5),('p95',.95),('p99',.99),('max',1)]},'max_optimistic_error_bps':max([max(0,r['price_error_bps']*(1 if side=='sell' else -1)) for r in rs],default=None)}
print(json.dumps({'sides':sides,'quote_counts':quotes,'predictions':rows,'failures':fails,'limitations':['Observed successful swaps only; does not estimate rejected fills','Source-only ignores provider guards and expiry','Internal extension state remains approximate','Execution-state order baseline; log availability is not Nitro-only latency','Observed trade sizes, not a 500 USDG profit backtest']},indent=2))
