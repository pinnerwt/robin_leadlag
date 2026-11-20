"""Initialization-only bulk account witnesses through BALANCE opcode tracing.
Contracts are never called: Multicall3.getEthBalance only reads each address.
No overrides, inferred nonces, or runtime RPC fallback.
"""
from bootstrap_batch import aggregate,MULTICALL,merge
from bootstrap_state import selector,word
from concurrent.futures import ThreadPoolExecutor

def read_accounts(bootstrap,block,addresses,batch_size=400):
 out={'accounts':{}};addresses=sorted({a.lower() for a in addresses})
 sig=selector('getEthBalance(address)')
 def fetch(group):
  request=aggregate([dict(to=MULTICALL,data=sig+word(int(a,16)).hex()) for a in group])
  accounts=bootstrap.trace(request,block)
  missing=[a for a in group if a not in accounts]
  # Geth's prestate tracer omits some precompiles. Read explicit metadata at
  # this same initialization block; do not infer zero balance/nonce/code.
  for address in missing:
   code=bootstrap.rpc('eth_getCode',[address,block])
   balance=bootstrap.rpc('eth_getBalance',[address,block])
   nonce=bootstrap.rpc('eth_getTransactionCount',[address,block])
   accounts[address]={'balance':balance,'nonce':int(nonce,16),'code':code}
  return accounts
 # Bootstrap.rpc retains its shared request-rate limiter; parallelism overlaps
 # response latency without increasing the configured launch rate.
 groups=[addresses[start:start+batch_size] for start in range(0,len(addresses),batch_size)]
 with ThreadPoolExecutor(max_workers=4) as executor:
  for accounts in executor.map(fetch,groups):merge(out,accounts)
 return out['accounts']
