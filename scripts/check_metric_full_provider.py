"""Offline provider fidelity audit on accepted calldata and observed pool transitions."""
import json,subprocess,collections,concurrent.futures,argparse
p=argparse.ArgumentParser();p.add_argument("--calibrated",action="store_true");p.add_argument("--base",default="reports/metric-multi-latest");args=p.parse_args();CALIBRATED=args.calibrated
from pathlib import Path
B=Path(args.base)
def check(m):
 s=json.load(open(m['seed']));anchor=int(s['anchor']['number'],16)
 p=subprocess.Popen(['target/release/examples/spcx_state_worker',m['seed'],'--source-only' if CALIBRATED else '--provider-full'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def call(r):
  p.stdin.write(json.dumps(r)+'\n');p.stdin.flush();return json.loads(p.stdout.readline())
 rows=[json.loads(l)for l in open(B/(m['symbol']+'-events.jsonl'))];rows=[r for r in rows if r['kind']!='session'and r.get('block_number')and int(r['block_number'],16)>anchor]
 rows.sort(key=lambda r:(int(r['block_number'],16),int(r.get('transaction_index','0x0'),16)))
 counts=collections.Counter();errors=collections.Counter();maxerr=0;examples=[]
 try:
  for r in rows:
   if r['kind']=='oracle_candidate':
    if 'accepted_log_ns'not in r:continue
    call(dict(kind='source',word=r['word']))
    if CALIBRATED:counts['source_updates']+=1;continue
    # Check all source transitions without Binance tick processing.
    out=call(dict(kind='provider_prices',header=r['header']));counts['provider_probes']+=1
    if 'error'in out:errors[out['error']]+=1
    else:counts['provider_priced']+=1
   else:
    out=call(dict(kind='pool',logs=r['logs'],header=r['header']))
    if 'error'in out:
     errors['pool:'+out['error']]+=1
     # Continuing after unknown pool state cannot validate later swaps.
     counts['stopped_on_pool_error']=1;break
    d=out['result']['diagnostic'];counts['swaps']+=d['swap_count'];counts['mismatches']+=d['token_mismatch_count'];maxerr=max(maxerr,d['max_price_error_bps'])
    if d['token_mismatch_count']and len(examples)<3:examples.append(dict(tx=r['tx'],diagnostic=d))
 finally:p.stdin.close();p.wait();p.stdout.close()
 out=dict(symbol=m['symbol'],counts=dict(counts),errors=dict(errors),max_price_error_bps=maxerr,mismatch_examples=examples)
 (B/(m['symbol']+('-calibrated-audit.json' if CALIBRATED else '-provider-audit.json'))).write_text(json.dumps(out,indent=2)+'\n');print(m['symbol'],dict(counts),dict(errors),maxerr,flush=True)
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as ex:list(ex.map(check,json.load(open(B/('calibrated-manifest.json' if CALIBRATED else 'manifest.json')))))
