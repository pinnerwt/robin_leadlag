"""Offline calldata-only V3 state experiment. stdin: decode_feed --with-raw JSONL.
Logs ONLY validate/invalidate; never copy their prices/liquidity into the state.
Unknown routers, missing transitions or speculative failures disable quotes.
All proposals remain non-executable: full transaction success is not emulated.
"""
import argparse,copy,json,sys,time
from decimal import Decimal
from pathlib import Path
from collections import Counter
from v3_state import State,amount0,amount1,sqrt_tick
from v3_calldata import decode,signed
SWAP='0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67'
MINT='0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde'
BURN='0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c'
ROUTERS={'0xcaf681a66d020601342297493863e78c959e5cb2','0x8876789976decbfcbbbe364623c63652db8c0904'}
class Book:
 def __init__(self,seed,packed_registry=None,assume_success=False):
  if not seed.get('complete'):raise ValueError('incomplete checkpoint')
  if packed_registry and packed_registry['anchor_hash']!=seed['anchor']['hash']:raise ValueError('router and pool checkpoints must share one anchor')
  self.delegated_pins_stale=False
  self.assume_success=assume_success
  self.packed_registry=packed_registry
  self.meta={p['pool']:p for p in seed['pools']};self.states={a:State.load(p) for a,p in self.meta.items()};self.invalid={};self.expected={};self.unsupported={};self.partial={};self.counts=Counter()
 def observe_envelope(self,tx):
  # A type-4 envelope can change any account's delegation, including accounts
  # other than tx.to. Invalidate all delegated pins until a new checkpoint.
  raw=tx.get('raw_transaction','')
  if not raw or raw.lower().startswith('0x04'):self.delegated_pins_stale=True
 def proposal(self,tx):
  self.observe_envelope(tx)
  profile=(self.packed_registry or {}).get('routers',{}).get((tx.get('to') or '').lower(),{})
  if profile.get('profile')=='delegated-single-v3-v1':
   from delegated_book import proposal
   return proposal(self,tx,profile)
  try:ops=decode(tx['to'],tx['data'],self.meta,ROUTERS,packed_registry=self.packed_registry)
  except ValueError as e:self.unsupported[tx['tx']]=str(e);return []
  notes=sorted({op['coverage_note'] for op in ops if op.get('coverage_note')})
  if notes:self.partial[tx['tx']]=notes
  touched={op['pool'] for op in ops}
  if any(a in self.invalid for a in touched):return []
  candidate={a:copy.deepcopy(self.states[a]) for a in touched};expected=[]
  try:
   for op in ops:
    state=candidate[op['pool']]
    if op['kind']=='swap':
     result=state.swap(op['zero'],op['amount'],op['limit'],True)
     if op['constraint'] and not self.assume_success:
      c=op['constraint'];inp=max(result['amount0'],result['amount1']);out=-min(result['amount0'],result['amount1'])
      if c['kind']=='min_out' and out<c['amount'] or c['kind']=='max_in' and inp>c['amount']:raise ValueError('router slippage constraint')
     if op['amount']<0 and result['unfilled']:raise ValueError('partial exact output')
     expected.append((op['pool'],dict(kind='swap',**result)))
    else:
     lower,upper,delta=op['lower'],op['upper'],op['delta'];lo,hi=sqrt_tick(lower),sqrt_tick(upper);mint=delta>=0;liquidity=abs(delta)
     a0=amount0(max(lo,state.sqrt),hi,liquidity,mint) if state.tick<upper else 0
     a1=amount1(lo,min(hi,state.sqrt),liquidity,mint) if state.tick>=lower else 0
     state.modify(lower,upper,delta)
     expected.append((op['pool'],dict(kind='mint' if mint else 'burn',lower=lower,upper=upper,amount=liquidity,amount0=a0,amount1=a1)))
  except ValueError as e:
   for a in touched:self.invalid[a]='calldata simulation rejected: '+str(e)
   self.counts['simulation_rejected']+=1;return []
  self.states.update(candidate);self.expected[tx['tx']]=expected;self.counts['decoded_transactions']+=1
  return sorted(touched)
 def validate(self,log):
  a=log['address'].lower()
  if a not in self.meta:return
  if log.get('removed'):self.invalid[a]='removed log';return
  topic=log['topics'][0]
  if topic not in (SWAP,MINT,BURN):
   self.invalid[a]='unhandled pool event';self.counts['unhandled_pool_events']+=1;return
  tx=log['transactionHash'];expected=self.expected.get(tx,[])
  if not expected:
   self.invalid[a]=self.unsupported.get(tx,'missing decoded calldata transition');self.counts['unhandled_transitions']+=1;return
  pool,want=expected.pop(0);raw=bytes.fromhex(log['data'][2:]);v=[int.from_bytes(raw[i:i+32],'big') for i in range(0,len(raw),32)]
  if topic==SWAP:got=dict(kind='swap',amount0=signed(v[0]),amount1=signed(v[1]),sqrt=v[2],liquidity=v[3],tick=signed(v[4]))
  else:
   offset=1 if topic==MINT else 0
   got=dict(kind='mint' if topic==MINT else 'burn',lower=signed(int(log['topics'][2],16)),upper=signed(int(log['topics'][3],16)),amount=v[offset],amount0=v[offset+1],amount1=v[offset+2])
  if pool!=a or any(got[k]!=want.get(k) for k in got):self.invalid[a]='calldata transition parity mismatch';self.counts['transition_mismatch']+=1
  else:self.counts[got['kind']+'_matches']+=1
 def quotes(self,a,sizes,tx):
  p=self.meta[a];state=self.states[a];base=p['base_index'];out=[]
  for size in sizes:
   record=dict(kind='amm_state_quote',venue='uniswap_v3',pool=a,base_token=p['base_token'],quote_token=p['quote_token'],size_tokens=size,available_mono_ns=tx['mono_ns'],recv_ns=tx['recv_ns'],tx=tx['tx'],state_complete=False,executable=False,provisional=True,timing='calldata_arrival_excludes_offline_compute',phase='offline_reconstruction')
   try:
    if a in self.invalid:raise ValueError(self.invalid[a])
    amount=Decimal(size)*10**p['decimals'][base]
    if amount!=int(amount) or amount<=0:raise ValueError('invalid size')
    start=time.perf_counter_ns();sell=state.swap(base==0,int(amount));buy=state.swap(base!=0,-int(amount))
    if sell['unfilled'] or buy['unfilled']:raise ValueError('partial fill')
    scale=Decimal(10)**p['decimals'][1-base];key='amount'+str(1-base)
    record.update(bid=str(Decimal(abs(sell[key]))/scale/Decimal(size)),ask=str(Decimal(abs(buy[key]))/scale/Decimal(size)),bid_amount_raw=str(abs(sell[key])),ask_amount_raw=str(abs(buy[key])),compute_ns=time.perf_counter_ns()-start)
   except ValueError as e:record['reason']=str(e)
   out.append(record)
  return out

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('checkpoint');ap.add_argument('--packed-registry');ap.add_argument('--sizes',default='0.02,0.1');ap.add_argument('--report',default='reports/amm/calldata-replay.json');a=ap.parse_args();seed=json.load(open(a.checkpoint));book=Book(seed,json.load(open(a.packed_registry)) if a.packed_registry else None);anchor=seed['anchor']['hash'];started=False;seq=None;ignored=set();seen=set();early={};anchor_seen=False
 for line in sys.stdin:
  r=json.loads(line);kind=r['kind']
  if kind=='feed_block':
   if r['block_hash']==anchor:started=True;anchor_seen=True;ignored.add(anchor)
   if not started:ignored.add(r['block_hash']);continue
   n=int(r['sequence'])
   if seq is not None and n not in (seq,seq+1):
    for pool in book.meta:book.invalid[pool]='Nitro sequence discontinuity'
   seq=max(seq or n,n)
  elif kind=='feed_tx' and started and r['block_hash'] not in ignored:
   if r['tx'] in seen:continue
   seen.add(r['tx']);touched=book.proposal(r)
   for pool in touched:
    for quote in book.quotes(pool,a.sizes.split(','),r):print(json.dumps(quote,separators=(',',':')))
   for log in early.pop(r['tx'],[]):book.validate(log)
  elif kind=='chain_log' and started:
   log=r['payload']
   if int(log['blockNumber'],16)<=int(seed['anchor']['number'],16):continue
   if log['address'].lower() not in book.meta:continue
   if log['transactionHash'] in seen:book.validate(log)
   else:early.setdefault(log['transactionHash'],[]).append(log)
  elif kind=='gap' and started and r.get('stream')!='binance':
   for pool in book.meta:book.invalid[pool]='transport gap'
 if not anchor_seen:raise ValueError('checkpoint anchor not in pushed tape')
 for logs in early.values():
  for log in logs:book.validate(log)
 report=dict(status='partial_calldata_support',production_ready=False,checkpoint_anchor=anchor,counts=dict(book.counts),invalid_pools=book.invalid,pending_unmatched_swaps=sum(len(v) for v in book.expected.values()),raw_recording='all pools retained; no logs applied as state',coverage='only supported router/direct pool calls; proposals never executable')
 Path(a.report).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
