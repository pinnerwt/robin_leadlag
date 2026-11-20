import json,subprocess,collections,sys
b='reports/ohio-20ms-backtest/'
for symbol in (sys.argv[1:] or ['ETHUSDT','NVDABUSDT']):
 s=json.load(open(b+symbol+'-seed.json'));anchor=int(s['anchor']['number'],16)
 p=subprocess.Popen(['target/release/examples/spcx_state_worker',b+symbol+'-seed.json','--provider-full'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def call(r):
  p.stdin.write(json.dumps(r)+'\n');p.stdin.flush();return json.loads(p.stdout.readline())
 es=[json.loads(l) for l in open(b+symbol+'-events.jsonl')];es=[r for r in es if r.get('block_number') and int(r['block_number'],16)>anchor];es.sort(key=lambda r:(int(r['block_number'],16),int(r.get('transaction_index','0x0'),16),r['mono_ns']))
 c=collections.Counter();errors=[];maxerr=0
 for r in es:
  if r['kind']=='oracle_candidate':
   if 'accepted_log_ns' not in r:continue
   out=call(dict(kind='source',word=r['word']))
  elif r['kind']=='aux_oracle':out=call(r)
  else:out=call(dict(kind='pool',logs=r['logs'],header=r['header']))
  if 'error' in out:
   errors.append(dict(kind=r['kind'],tx=r['tx'],error=out['error'],header=r['header']));break
  c[r['kind']]+=1
  if r['kind']=='pool_transaction':
   d=out['result']['diagnostic'];c['swaps']+=d['swap_count'];c['mismatch']+=d['token_mismatch_count'];maxerr=max(maxerr,d['max_price_error_bps'])
 p.stdin.close();p.wait()
 result=dict(symbol=symbol,counts=dict(c),errors=errors,max_price_error_bps=maxerr);print(result,flush=True);open(b+symbol+'-aux-audit.json','w').write(json.dumps(result,indent=2))
