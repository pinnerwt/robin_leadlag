"""Trace-free, fixed-block refresh of a known sparse checkpoint.
Every known account/code/storage value is refreshed, never silently reused.
Published only after local EVM outputs match fresh RPC quote fixtures.
"""
import argparse,copy,json,time,urllib.request,urllib.error,subprocess,re
from decimal import Decimal,ROUND_FLOOR
from pathlib import Path
from bootstrap_state import unpack,simulate
from bootstrap_batch import aggregate,split

class BatchRpc:
 def __init__(self,url,batch_size=5,interval=1.2):self.url=url;self.size=batch_size;self.interval=interval;self.next=0;self.calls=0
 def many(self,calls):
  values=[]
  for start in range(0,len(calls),self.size):
   part=calls[start:start+self.size];time.sleep(max(0,self.next-time.monotonic()));self.next=time.monotonic()+self.interval
   payload=[dict(jsonrpc='2.0',id=i,method=m,params=p)for i,(m,p)in enumerate(part)]
   req=urllib.request.Request(self.url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','User-Agent':'robin-leadlag/0.1'})
   for attempt in range(5):
    try:
     with urllib.request.urlopen(req,timeout=45)as response:rows=json.load(response)
     break
    except urllib.error.HTTPError as exc:
     if exc.code!=429 or attempt==4:raise
     delay=max(float(exc.headers.get("Retry-After",0)),2**(attempt+1));print("rpc_rate_limit", "completed",self.calls,"retry_seconds",delay,flush=True);time.sleep(delay)
   if not isinstance(rows,list):raise ValueError('RPC did not return batch')
   ids=[r.get('id')for r in rows]
   if len(ids)!=len(set(ids))or set(ids)!=set(range(len(part))):raise ValueError('RPC batch IDs incomplete/duplicated')
   byid={r['id']:r for r in rows}
   for i in range(len(part)):
    if 'error'in byid[i]:raise RuntimeError(json.dumps(byid[i]['error']))
    values.append(byid[i]['result'])
   self.calls+=len(part)
   if self.calls//200!=(self.calls-len(part))//200:print("rpc_progress",self.calls,flush=True)
  return values
 def one(self,method,params):return self.many([(method,params)])[0]

def main():
 p=argparse.ArgumentParser();p.add_argument('--template',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rpc',required=True);p.add_argument('--config',required=True);p.add_argument('--sizes',default='0.02,0.1');p.add_argument('--batch-size',type=int,default=5);p.add_argument('--batch-interval',type=float,default=1.2);a=p.parse_args()
 if a.batch_size<=0 or a.batch_interval<=0:raise ValueError('invalid batch limits')
 rpc=BatchRpc(a.rpc,a.batch_size,a.batch_interval);seed=copy.deepcopy(json.load(open(a.template)));head=rpc.one('eth_getBlockByNumber',['latest',False]);block=head['number'];print('anchor',block,head['hash'],flush=True)
 configured={p['pool'].lower()for p in json.load(open(a.config))['pools']}
 if {p['pool'].lower()for p in seed['pools']}!=configured:raise ValueError('template pool catalog mismatch')
 seed.update(anchor=head,created_ns=time.time_ns(),failed=[],anchor_verified=False,storage_complete=False,rpc_phase='known_slot_recovery_only',recovery_template=a.template)
 calls=[];targets=[]
 for address,account in seed['accounts'].items():
  account.pop('complete_hashed_storage',None)
  for field,method in [('code','eth_getCode'),('balance','eth_getBalance'),('nonce','eth_getTransactionCount')]:calls.append((method,[address,block]));targets.append((account,field))
  for slot in account.get('storage',{}):calls.append(('eth_getStorageAt',[address,slot,block]));targets.append((account['storage'],slot))
 for (obj,key),v in zip(targets,rpc.many(calls)):obj[key]=v
 def aggregate_at(calls):
  rows=split(rpc.one('eth_call',[aggregate(calls),block]))
  if len(rows)!=len(calls):raise ValueError('aggregate length')
  return rows
 for p,(ok,value)in zip(seed['pools'],aggregate_at([dict(to=p['pool'],data='0xbcdb4dad')for p in seed['pools']])):
  if not ok or value!=p['immutables']:raise ValueError('immutable/template mismatch: '+p['pair'])
  p['storage']=dict(seed['accounts'][p['pool'].lower()]['storage']);p['quote_checks']=[]
 for p,(ok,value)in zip(seed['pools'],aggregate_at([dict(to=p['provider'],data='0x171755b1')for p in seed['pools']])):
  if not ok or len(value)!=194:raise ValueError('provider quote unavailable: '+p['pair'])
  p['quote_trace']=dict(output=value,error=None,from_address='0xca11bde05977b3631167028862be2a173976ca11')
 for p in seed['pools']:
  checks=[]
  mid=Decimal(unpack(p['quote_trace']['output'])[2])/Decimal(2**64)
  cap_size=str((Decimal(500)/mid).quantize(Decimal(10)**-p['decimals'][0],rounding=ROUND_FLOOR))
  for size in [*a.sizes.split(','),'1000000',cap_size]:
   q=int(Decimal(size)*10**p['decimals'][0])
   for sell in (True,False):checks.append(dict(seed_only=size=='1000000',size_tokens=size,side='bid'if sell else'ask',call=simulate(p['pool'],sell,q if sell else-q,unpack(p['quote_trace']['output']))))
  for check,(ok,value)in zip(checks,aggregate_at([c['call']for c in checks])):check.update(expected=value,error=None if ok else'execution reverted')
  p['quote_checks']=checks
 if rpc.one('eth_getBlockByNumber',[block,False])['hash']!=head['hash']:raise ValueError('anchor reorg')
 seed.update(anchor_verified=True,finished_ns=time.time_ns(),rpc_calls=rpc.calls)
 candidate=a.output.with_suffix('.candidate.json');candidate.write_text(json.dumps(seed,separators=(',',':')))
 discovered=[]
 for attempt in range(33):
  check=subprocess.run(['target/release/examples/check_checkpoint',str(candidate)],capture_output=True,text=True,check=True)
  rows=json.loads(check.stdout);bad=[r for r in rows if r.get('match')is not True]
  a.output.with_suffix('.parity.json').write_text(json.dumps(rows,indent=2)+'\n')
  if not bad:break
  missing=set()
  for row in bad:
   match=re.search(r'unknown slot (0x[0-9a-fA-F]{40}) (0x[0-9a-fA-F]+)',row.get('error',''))
   if not match:raise ValueError(f'local parity mismatch without recoverable slot: {row}')
   address,slot=(x.lower()for x in match.groups())
   if address not in seed['accounts']or slot in seed['accounts'][address]['storage']:raise ValueError('unrecoverable dependency')
   missing.add((address,slot))
  if attempt==32 or len(discovered)+len(missing)>256:raise ValueError('slot discovery budget exceeded')
  ordered=sorted(missing)
  for (address,slot),value in zip(ordered,rpc.many([('eth_getStorageAt',[address,slot,block])for address,slot in ordered])):seed['accounts'][address]['storage'][slot]=value
  discovered.extend(ordered);print('discovered_slots',len(discovered),flush=True)
  for pool in seed['pools']:pool['storage']=dict(seed['accounts'][pool['pool'].lower()]['storage'])
  candidate.write_text(json.dumps(seed,separators=(',',':')))
 seed['discovered_slots']=discovered;seed['rpc_calls']=rpc.calls
 seed['finished_ns']=time.time_ns();seed['local_parity']=dict(passed=True,checks=len(rows));candidate.write_text(json.dumps(seed,separators=(',',':')));candidate.replace(a.output)
 print('complete',len(seed['pools']),'pools',len(rows),'parity checks','rpc_calls',rpc.calls,flush=True)
if __name__=='__main__':main()
