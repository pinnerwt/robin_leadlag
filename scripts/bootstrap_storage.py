"""Fixed-block initialization helper. Code override only exists in eth_call;
no transaction is sent. Runtime follower must not import this module.
"""
from bootstrap_batch import aggregate,split,MULTICALL
from concurrent.futures import ThreadPoolExecutor
GETTER='0x5f5b3681101560145780355481526020016001565b50365ff3'
def read_slots(rpc,block,requests):
 """requests: address -> explicit storage keys; returns canonical hex values."""
 # ArbOS hooks may mutate system storage even inside eth_call (e.g. calldata
 # units). Read that account directly; an overridden getter would see post-hook
 # values rather than the pinned checkpoint. This remains initialization-only.
 system='0xa4b05fffffffffffffffffffffffffffffffffff'
 out={a:{} for a in requests}
 for a,keys in requests.items():
  if a.lower()==system:
   for k in keys:
    key=int(k,16) if isinstance(k,str) else k
    out[a][hex(key)]=hex(int(rpc('eth_getStorageAt',[a,hex(key),block]),16))
 calls=[];jobs=[]
 for address,keys in requests.items():
  if address.lower()==system:continue
  ordered=sorted({int(k,16) if isinstance(k,str) else k for k in keys})
  for start in range(0,len(ordered),128):
   part=ordered[start:start+128];call=dict(to=address,data='0x'+''.join(k.to_bytes(32,'big').hex() for k in part))
   # Overriding the aggregate entrypoint itself would replace Multicall's ABI
   # dispatcher with the getter. Read its own slots separately.
   if address.lower()==MULTICALL:
    value=rpc('eth_call',[call,block,{address:{'code':GETTER}}]);raw=bytes.fromhex(value[2:])
    if len(raw)!=32*len(part):raise ValueError('Multicall self-storage getter failed')
    out[address].update({hex(k):hex(int.from_bytes(raw[32*i:32*i+32],'big')) for i,k in enumerate(part)})
   else:calls.append(call);jobs.append((address,part))
 groups=[];start=0
 while start<len(calls):
  end=start;slot_count=0
  # Keep the cold-SLOAD work bounded while filling short per-account batches.
  # 4096 slots used to require 32 calls of 128 slots; 32-slot prefixes can
  # instead share one request across 128 accounts.
  while end<len(calls) and end-start<128 and slot_count+len(jobs[end][1])<=4096:
   slot_count+=len(jobs[end][1]);end+=1
  groups.append((start,end))
  start=end
 def execute(group):
  overrides={c['to']:{'code':GETTER} for c in group}
  try:return split(rpc('eth_call',[aggregate(group),block,overrides]))
  except RuntimeError as error:
   if 'out of gas' not in str(error).lower() or len(group)<2:raise
   middle=len(group)//2
   return execute(group[:middle])+execute(group[middle:])
 # Independent fixed-block reads may overlap response latency. Bootstrap.rpc
 # still serializes request launch through its configured rate limiter.
 with ThreadPoolExecutor(max_workers=4) as executor:
  results=executor.map(lambda bounds:execute(calls[bounds[0]:bounds[1]]),groups)
  for (start,end),result in zip(groups,results):
   if len(result)!=end-start:raise ValueError('initialization batch count mismatch')
   for (address,keys),(ok,value) in zip(jobs[start:end],result):
    raw=bytes.fromhex(value[2:])
    if not ok or len(raw)!=32*len(keys):raise ValueError('initialization storage getter failed')
    out[address].update({hex(k):hex(int.from_bytes(raw[32*i:32*i+32],'big')) for i,k in enumerate(keys)})
 return out
