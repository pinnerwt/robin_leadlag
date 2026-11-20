"""Quote arbitrary token sizes from committed local-EVM writes. Zero RPC.
Proposals remain non-executable until the complete follower is independently
validated. This tool does NOT elevate a finite witness replay into production.
"""
import argparse,json,sys,time
from decimal import Decimal
from v3_storage_book import StorageBook
p=argparse.ArgumentParser(description=__doc__);p.add_argument('checkpoint');p.add_argument('layout',nargs='?');p.add_argument('--sizes',default='0.02,0.1');a=p.parse_args();
if a.checkpoint.endswith(('.bin','.bin.zst')):
 from tape import records
 frames=list(records([a.checkpoint]))
 if len(frames)!=2 or frames[0].get('kind')!='v3_checkpoint' or frames[1].get('kind')!='v3_layout':raise ValueError('unexpected checkpoint archive schema')
 seed=frames[0]['payload'];layout=frames[1]['payload']
 if frames[1]['anchor_hash']!=seed['anchor']['hash']:raise ValueError('layout anchor mismatch')
else:
 if not a.layout:raise ValueError('JSON checkpoint requires layout path')
 seed=json.load(open(a.checkpoint));layout=json.load(open(a.layout))
book=StorageBook(seed,layout);sizes=[Decimal(x) for x in a.sizes.split(',')];sequence=int(seed['anchor']['number'],16)
if any(not s.is_finite() or s<=0 for s in sizes):raise ValueError('sizes must be finite and positive')
for line in sys.stdin:
 r=json.loads(line)
 if r.get('checkpoint_hash')!=book.anchor:raise ValueError('EVM/quote checkpoint mismatch')
 if r.get('kind')=='block_state':
  if r['sequence']!=sequence+1:raise ValueError('block sequence discontinuity')
  sequence=r['sequence'];continue
 if r.get('sequence')!=sequence:raise ValueError('transaction without matching block marker')
 if r.get('error') or not r.get('committed'):raise ValueError('EVM transaction did not commit')
 if any(v.get('destroyed') for addr,v in r.get('accounts',{}).items() if addr in book.states):raise ValueError('pool destroyed')
 start=time.perf_counter_ns();touched=book.apply(r['changed_storage'],r.get('mapping_preimages',[]))
 for pool in touched:
  meta=book.meta[pool];base=meta['base_index'];scale=Decimal(10)**meta['decimals'][1-base]
  for size in sizes:
   raw=size*10**meta['decimals'][base]
   if raw!=int(raw):raise ValueError('size exceeds token precision')
   out=dict(kind='amm_state_quote',pool=pool,tx=r['tx'],sequence=sequence,size_tokens=str(size),recv_ns=r.get('recv_ns'),available_mono_ns=r.get('mono_ns'),state_source='committed_local_evm_storage',checkpoint_hash=book.anchor,executable=False,state_complete=False,provisional=True)
   try:
    q=book.quote_raw(pool,int(raw));out.update({k:str(v) for k,v in q.items()});out.update(bid=str(Decimal(q['bid_amount_raw'])/scale/size),ask=str(Decimal(q['ask_amount_raw'])/scale/size))
   except ValueError as e:out['reason']=str(e)
   out['reduce_and_quote_ns']=time.perf_counter_ns()-start;print(json.dumps(out,separators=(',',':')),flush=True)
