"""Strict decoder for standard V3 swaps, multicalls, and Universal Router V3 commands.
Decoded calls are speculative until execution is independently validated. No RPC.
"""
# Literal selectors avoid any subprocess on the live path.
DIRECT_SWAP='128acb08'
DIRECT_MINT='3c8a7d8d'
DIRECT_BURN='a34123a7'
EXACT_IN_SINGLE={'414bf389':True,'04e45aaf':False}
EXACT_OUT_SINGLE={'db3e2198':True,'5023b4df':False}
EXACT_IN={'c04b8d59':True,'b858183f':False}
EXACT_OUT={'f28c0498':True,'09b81346':False}
def word(d,i):
 raw=d[32*i:32*i+32]
 if len(raw)!=32:raise ValueError('truncated ABI')
 return int.from_bytes(raw,'big')
def signed(v):return v-(1<<256) if v>>255 else v
def address(v):
 if v>>160:raise ValueError('address padding')
 return '0x'+v.to_bytes(20,'big').hex()
def blob(d,offset):
 if offset<0 or offset+32>len(d):raise ValueError('dynamic offset')
 n=int.from_bytes(d[offset:offset+32],'big');out=d[offset+32:offset+32+n]
 if len(out)!=n:raise ValueError('truncated bytes')
 return out
def array(d,offset):
 if offset+32>len(d):raise ValueError('array offset')
 n=int.from_bytes(d[offset:offset+32],'big');base=offset+32
 if n>1024:raise ValueError('array too long')
 return [blob(d,base+word(d[base:],i)) for i in range(n)]
def path(p):
 if len(p)<43 or (len(p)-20)%23:raise ValueError('bad V3 path')
 return [('0x'+p[i:i+20].hex(),'0x'+p[i+23:i+43].hex(),int.from_bytes(p[i+20:i+23],'big')) for i in range(0,len(p)-20,23)]
def decode(to,calldata,pools,routers,depth=0,packed_registry=None):
 if not to:raise ValueError('contract creation initcode not decoded')
 # Known single-pool operations outside the recording universe are irrelevant.
 # Unknown addresses/indexes remain unknown: absence of a literal pool address
 # in packed calldata is not proof that a tracked pool is untouched.
 return [op for op in _decode(to,calldata,pools,routers,depth,packed_registry) if op is not None]

def _decode(to,calldata,pools,routers,depth=0,packed_registry=None):
 if depth>12:raise ValueError('multicall depth')
 raw=bytes.fromhex(calldata[2:]) if isinstance(calldata,str) else calldata
 sig=raw[:4].hex();d=raw[4:];to=to.lower()
 if packed_registry and to in packed_registry.get('routers',{}):
  from packed_routers import decode_packed
  ops=decode_packed(to,raw,packed_registry,tracked_pools=pools)
  if any(op.get('coverage_note') and op['pool'] not in pools for op in ops):
   raise ValueError('unrecorded outer pool has unresolved callback dependencies')
  return [op for op in ops if op['pool'] in pools]
 if to in pools:
  if sig==DIRECT_SWAP:
   zero=word(d,1)
   if zero not in (0,1):raise ValueError('bool')
   return [dict(kind='swap',pool=to,zero=bool(zero),amount=signed(word(d,2)),limit=word(d,3),constraint=None)]
  if sig in (DIRECT_MINT,DIRECT_BURN):
   i=1 if sig==DIRECT_MINT else 0
   return [dict(kind='liquidity',pool=to,lower=signed(word(d,i)),upper=signed(word(d,i+1)),delta=word(d,i+2)*(1 if sig==DIRECT_MINT else -1))]
  # These do not change price, active liquidity or ticks.
  if sig in ('4f1eb3d8','8206a4d1'):return [] # collect, setFeeProtocol
  raise ValueError('unsupported direct pool selector '+sig)
 if to not in routers:raise ValueError('unknown router '+to+' selector '+sig)
 if sig in ('ac9650d8','5ae401dc','1f0464d1'):
  off=word(d,0 if sig=='ac9650d8' else 1)
  return [op for child in array(d,off) for op in decode(to,child,pools,routers,depth+1,packed_registry)]
 def route(tokenin,tokenout,fee,amount,limit,constraint):
  found=[a for a,p in pools.items() if p['fee']==fee and set(p['tokens'])=={tokenin,tokenout}]
  if not found:return None
  if len(found)!=1:raise ValueError('ambiguous tracked pool')
  a=found[0];return dict(kind='swap',pool=a,zero=tokenin==pools[a]['tokens'][0],amount=amount,limit=limit or None,constraint=constraint)
 if sig in EXACT_IN_SINGLE or sig in EXACT_OUT_SINGLE:
  exact=sig in EXACT_IN_SINGLE;deadline=(EXACT_IN_SINGLE if exact else EXACT_OUT_SINGLE)[sig];i=5 if deadline else 4
  return [route(address(word(d,0)),address(word(d,1)),word(d,2),word(d,i)*(1 if exact else -1),word(d,i+2),dict(kind='min_out' if exact else 'max_in',amount=word(d,i+1)))]
 if sig in EXACT_IN or sig in EXACT_OUT:
  exact=sig in EXACT_IN;deadline=(EXACT_IN if exact else EXACT_OUT)[sig];body=d[word(d,0):];hops=path(blob(body,word(body,0)));i=3 if deadline else 2
  if len(hops)!=1:raise ValueError('multihop V3 needs transaction-wide callback semantics')
  a,b,f=hops[0]
  return [route(a if exact else b,b if exact else a,f,word(body,i)*(1 if exact else -1),None,dict(kind='min_out' if exact else 'max_in',amount=word(body,i+1)))]
 if sig in ('3593564c','24856bc3'):
  commands=blob(d,word(d,0));inputs=array(d,word(d,1))
  if len(commands)!=len(inputs):raise ValueError('command input mismatch')
  result=[]
  for command,body in zip(commands,inputs):
   command&=0x7f
   if command not in (0,1):raise ValueError('unsupported Universal Router command '+str(command))
   hops=path(blob(body,word(body,3)))
   if len(hops)!=1:raise ValueError('multihop universal V3')
   a,b,f=hops[0];exact=command==0;amount=word(body,1)
   if amount==1<<255:raise ValueError('router contract-balance amount requires balance state')
   result.append(route(a if exact else b,b if exact else a,f,amount if exact else -amount,None,dict(kind='min_out' if exact else 'max_in',amount=word(body,2))))
  return result
 raise ValueError('unsupported router selector '+sig)
