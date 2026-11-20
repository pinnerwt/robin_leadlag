"""Persistent local Metric EVM worker; arbitrary-size multi-pool quote interface.

No network access. This module does not assert transition coverage or launch
capture. The owner supplies ordered updates and independently tracks validity.
"""
from decimal import Decimal,localcontext
import json,selectors,subprocess,time
from pathlib import Path

class TransitionRejected(ValueError):pass

class MetricWorker:
 def __init__(self,checkpoint,*,executable='target/release/examples/metric_transition',timeout=30):
  seed=json.loads(Path(checkpoint).read_text());self.anchor=seed['anchor'];self.header=seed.get('parent_header',self.anchor)
  self.pools={p['pool'].lower():p for p in seed['pools']};self.timeout=timeout;self.valid=True
  self.process=subprocess.Popen([executable,str(checkpoint)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
  self.selector=selectors.DefaultSelector();self.selector.register(self.process.stdout,selectors.EVENT_READ)
 def request(self,request):
  if not self.valid:raise RuntimeError('worker invalid; checkpoint reload required')
  try:
   self.process.stdin.write(json.dumps(request)+'\n');self.process.stdin.flush()
   if not self.selector.select(self.timeout):raise TimeoutError('local Metric worker acknowledgement timed out')
   line=self.process.stdout.readline()
   if not line:raise RuntimeError('local Metric worker exited')
   response=json.loads(line)
   if 'error' in response:raise TransitionRejected(response['error'])
   result=response['result']
   if result['committed'] is not bool(request.get('commit',False)):raise ValueError('invalid commit acknowledgement')
   return result
  except TransitionRejected:raise
  except Exception:
   self.valid=False;self.close();raise
 def update_oracle(self,transaction):
  header={'timestamp':hex(int(transaction['timestamp'])),'l1BlockNumber':hex(int(transaction['l1_block']))}
  try:r=self.request(dict(kind='oracle_update',header=header,transaction={k:transaction[k] for k in ('to','from','data')},commit=True))
  except Exception:self.valid=False;raise
  self.header=header;return r
 def quote(self,pool,size,*,header=None):
  p=self.pools[pool.lower()];started=time.monotonic_ns()
  with localcontext() as ctx:
   ctx.prec=100
   quantity=Decimal(str(size));scale0=10**int(p['decimals'][0]);scale1=10**int(p['decimals'][1]);raw=quantity*scale0
   if not raw.is_finite() or raw<=0 or raw!=raw.to_integral_value() or raw>=1<<127:raise ValueError('invalid exact base-token size')
   sender='0xca11bde05977b3631167028862be2a173976ca11'
   common=dict(pool=pool.lower(),header=header or self.header,sender=sender,recipient=sender,commit=False)
   record=dict(kind='metric_quote',pool=pool.lower(),pair=p.get('pair'),binance_symbol=p.get('binance_symbol'),size_tokens=str(size),base_amount_raw=str(int(raw)),state_complete=False,executable=False,quote_source='local_state',status='unavailable')
   try:
    sell=self.request(dict(common,zero=True,amount=str(int(raw))))
    buy=self.request(dict(common,zero=False,amount=str(-int(raw))))
    bid=-int(sell['amount1']);ask=int(buy['amount1'])
    if bid<=0 or ask<=0:raise TransitionRejected('nonpositive quote amount')
    record.update(status='priced',bid_amount_raw=str(bid),ask_amount_raw=str(ask),bid=str(Decimal(bid)/scale1/quantity),ask=str(Decimal(ask)/scale1/quantity))
   except TransitionRejected as e:record['reason']=str(e)
  record.update(local_compute_ns=time.monotonic_ns()-started,available_ns=time.time_ns(),available_mono_ns=time.monotonic_ns())
  return record
 def close(self):
  self.valid=False
  if self.process.poll() is None:
   self.process.terminate()
   try:self.process.wait(timeout=5)
   except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
  self.selector.close()
  for pipe in (self.process.stdin,self.process.stdout):
   if pipe:pipe.close()
 def __enter__(self):return self
 def __exit__(self,*_):self.close()
