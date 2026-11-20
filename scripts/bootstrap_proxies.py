"""Initialize explicit EIP-1967 references; never run in the follower hot path."""
from bootstrap_accounts import read_accounts
from bootstrap_storage import read_slots

IMPLEMENTATION=int('360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc',16)
BEACON=int('a3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50',16)

def push_constants(code):
 raw=bytes.fromhex(code.removeprefix('0x'));i=0;values=set()
 while i<len(raw):
  op=raw[i];i+=1
  if 0x60<=op<=0x7f:
   size=op-0x5f
   if i+size>len(raw):break
   values.add(int.from_bytes(raw[i:i+size],'big'));i+=size
 return values

def hydrate_proxies(bootstrap,block,accounts,max_depth=8):
 """Read known proxy pointers found as bytecode immediates, not arbitrary slots.
 Beacon target code is captured; beacon-specific storage still needs coverage.
 """
 seen=set();references=[]
 for _ in range(max_depth):
  requests={}
  for address,account in accounts.items():
   if address in seen:continue
   seen.add(address)
   keys=push_constants(account.get('code','0x')) & {IMPLEMENTATION,BEACON}
   if keys:requests[address]=sorted(keys)
  if not requests:return references
  values=read_slots(bootstrap.rpc,block,requests);targets=set()
  for address,slots in values.items():
   dst=accounts[address].setdefault('storage',{})
   for key,value in slots.items():
    old=next((v for k,v in dst.items() if int(k,16)==int(key,16)),None)
    if old is not None and int(old,16)!=int(value,16):raise ValueError('proxy anchor disagreement')
    dst[key]=value
    # EVM address conversion uses the low 160 bits of the storage word.
    pointer=int(value,16)&((1<<160)-1)
    if pointer:
     target='0x'+pointer.to_bytes(20,'big').hex();targets.add(target)
     references.append(dict(proxy=address,slot=key,target=target))
  missing=targets-accounts.keys()
  if missing:
   fetched=read_accounts(bootstrap,block,missing)
   for address in missing:accounts[address]={k:v for k,v in fetched[address].items() if k!='storage'}
 raise ValueError('proxy initialization depth exceeded')
