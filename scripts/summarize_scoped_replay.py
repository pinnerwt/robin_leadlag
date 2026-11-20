"""Summarize experimental quote coverage without equating pricing with correctness."""
import argparse,collections,json
p=argparse.ArgumentParser();p.add_argument('input');a=p.parse_args()
counts=collections.Counter();reasons=collections.Counter();ranges={};failures=[]
for line in open(a.input):
 r=json.loads(line);counts[r['kind']]+=1
 if r['kind']=='state_quote':
  key='priced' if r.get('model_priced') else 'unavailable';counts[key]+=1
  if r.get('reason'):reasons[r['reason']]+=1
  if r.get('model_priced'):
   v=ranges.setdefault(r['size_tokens'],{'first_ns':r['available_mono_ns'],'last_ns':0,'count':0});v['last_ns']=r['available_mono_ns'];v['count']+=1
 elif 'failure' in r['kind']:failures.append(r)
print(json.dumps(dict(counts=counts,reasons=reasons,ranges=ranges,failures=failures[:20],note='Experimental model coverage only; error quantiles require independent swap/quote comparisons.'),indent=2))
