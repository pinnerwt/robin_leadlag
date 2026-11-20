"""Verified packed formats. No ABI guessing, network reads or log-derived amounts.
These describe attempted calls, not transaction success or callback validity.
"""
MASK256=(1<<256)-1
MASK160=(1<<160)-1
ROUTER_C33='0xc33acc93942105c57602e59e8e448c20ba718a85'
ROUTER_29='0x29d8d0a5c38716ebb4ae1786a46cf0ab74d480db'
ROUTER_7DEC='0x7dec8663bc55f3419a130fac7a7209b959ed8d90'
ROUTER_769='0x7693900963049c5401d12af0265f619729a4e94a'
ROUTER_9E='0x9e9ead6e46268a45c7559c8dfa5a778bad6ad331'
ROUTER_278='0x278d858f05b94576c1e6f73285886876ff6ef8d2'
ROUTER_520='0x520ed467860d840ec6ca20f1dacb9c0fa5168aa7'
ROUTER_610='0x61083b541a5851d373cf01c22dde3946d14a0525'
def decode_packed(to,calldata,registry,tracked_pools=None):
 to=to.lower();raw=bytes.fromhex(calldata[2:]) if isinstance(calldata,str) else calldata
 profile=registry.get('routers',{}).get(to)
 if not profile:raise ValueError('router not in pinned packed registry')
 if to==ROUTER_610:
  if profile.get('profile')!='610-fixed-v3-v1' or not profile.get('code_hash'):raise ValueError('unversioned 610 profile')
  if len(raw)!=59 or raw[2]>3:raise ValueError('610 framing or flags not verified')
  amount=int.from_bytes(raw[3:19],'big')
  if not amount:raise ValueError('610 zero amount')
  if raw[2]&2:amount=-amount
  limit=int.from_bytes(raw[19:39],'big')
  return [dict(kind='swap',pool='0x'+raw[39:59].hex(),zero=bool(raw[2]&1),amount=amount,
      limit=limit,constraint=None,decoder='610-fixed-v3-v1',
      execution_conditions=dict(l1_block_deadline=limit&0xffffffff,
          price_gate='current sqrt > limit' if raw[2]&1 else 'current sqrt < limit'))]
 if to=='0x204faca1764b154221e35c0d20abb3c525710498':
  if profile.get('profile')!='204f-permit-v3-v1' or not profile.get('code_hash'):raise ValueError('unversioned Universal profile')
  from universal_permit_route import decode
  return decode(raw,tracked_pools)
 if to=='0xc9a1dcff54632b408f2b0e048d8b7d3261697144':
  if profile.get('profile')!='c9-callback-v1' or not profile.get('code_hash') or not profile.get('implementation_code_hash'):raise ValueError('unversioned proxy profile')
  from c9_router import decode_c9
  return decode_c9(raw,tracked_pools)
 if to==ROUTER_7DEC and raw and raw[0] in (0x2f,0x31):
  if profile.get('profile')!='7dec-memory-word-v1' or not profile.get('code_hash'):raise ValueError('unversioned custom profile')
  if len(raw)!=89 or raw[88]!=3:raise ValueError('7dec continuation or length not verified')
  position=raw[43]
  if not 0x44<=position<=0x60:raise ValueError('7dec copy would overwrite non-amount fields')
  amount_bytes=bytearray([0xff if raw[0]==0x31 else 0]*32)
  offset=position-0x44
  amount_bytes[offset:offset+4]=raw[44:48]
  amount=int.from_bytes(amount_bytes,'big',signed=True)
  return [dict(kind='swap',pool='0x'+raw[68:88].hex(),zero=raw[0]==0x31,amount=amount,
      limit=int.from_bytes(raw[48:68],'big'),constraint=None,decoder='7dec-memory-word-v1')]
 if to=='0x4262efbd176f02824af27010bea218429c33c7e8':
  from nested_routers import decode_426
  return decode_426(raw,profile,tracked_pools)
 if to==ROUTER_769 and raw[:4].hex()=='b7bee4b6':
  if profile.get('profile')!='769-single-v3-v1' or not profile.get('code_hash'):raise ValueError('unversioned custom profile')
  from v3_calldata import word,blob,address
  d=raw[4:]
  offset=word(d,0)
  if offset!=128 or word(d[offset:],0)!=1:raise ValueError('769 requires one verified root action')
  base=offset+32
  if word(d[base:],0)!=32:raise ValueError('769 tuple array offset')
  action=d[base+32:]
  if action[:4].hex()!='2c2ecbc6' or any(action[4:32]) or word(action,1)!=64:raise ValueError('769 action not verified')
  payload=blob(action,64)
  if word(payload,0)!=32:raise ValueError('769 swap tuple offset')
  body=payload[32:]
  pool,tokenin,tokenout=[address(word(body,i)) for i in (0,1,2)]
  if word(body,3)!=0 or word(body,6)!=1:raise ValueError('769 swap modes not verified')
  amount=word(body,4);limit=word(body,5)
  if not 0<amount<(1<<255) or not 0<limit<=MASK160:raise ValueError('769 dynamic amount or invalid limit')
  offset=word(body,7)
  if offset!=256 or word(body[offset:],0)!=1:raise ValueError('769 callback array not verified')
  base=offset+32
  if word(body[base:],0)!=32:raise ValueError('769 callback tuple offset')
  callback=body[base+32:]
  if callback[:4].hex()!='67557586' or any(callback[4:32]) or word(callback,1)!=64:raise ValueError('769 callback selector not verified')
  blob(callback,64) # bounds-check the retained settlement payload
  return [dict(kind='swap',pool=pool,zero=int(tokenin,16)<int(tokenout,16),amount=amount,
      limit=limit,constraint=None,decoder='769-single-v3-v1',
      coverage_note='first swap decoded; embedded settlement callback not executed')]
 if to==ROUTER_29 and raw[:4].hex() in ('9c909e3f','e22092ea','164cb8f5'):
  if profile.get('profile')!='29-record55-v1' or not profile.get('code_hash'):raise ValueError('unversioned custom profile')
  intents=inspect_29(raw)
  if len(intents)!=1 and raw[:4].hex()!='164cb8f5':raise ValueError('29 multiple-record branch not verified')
  result=[]
  for intent in intents:
   index=str(intent['pool_index']);pool=profile['pool_indexes'].get(index)
   if not pool:raise ValueError('unknown packed pool index '+index)
   if tracked_pools is not None and pool not in tracked_pools:continue
   config=profile.get('pool_configs',{}).get(index)
   if config is None or ((int(config,16)>>160)&0xffffff)!=0x010002:raise ValueError('29 pool config branch not verified')
   if intent['flags']>7:raise ValueError('29 flags not verified')
   if intent['balance_cap']:raise ValueError('29 amount requires local vault token balance')
   result.append(dict(kind='swap',pool=pool,zero=intent['zero'],amount=intent['requested_amount']*(-1 if intent['exact_output'] else 1),
       limit=intent['limit'],constraint=None,decoder='29-record55-v1',
       attempt_policy='assume_subcall_success' if raw[:4].hex()=='164cb8f5' else 'assume_transaction_success'))
  return result
 if to==ROUTER_9E and raw[:4].hex() in ('00000000','01000000'):
  if profile.get('profile')!='9e-fallback-v1' or not profile.get('code_hash'):raise ValueError('unversioned custom profile')
  if len(raw)!=133:raise ValueError('9e fallback requires 133 bytes')
  if any(raw[53:73]):raise ValueError('9e nonzero reference branch not verified')
  amount=int.from_bytes(raw[1:33],'big');amount=amount-(1<<256) if amount>>255 else amount
  return [dict(kind='swap',pool='0x'+raw[73:93].hex(),zero=not bool(raw[0]&1),
      amount=amount,limit=int.from_bytes(raw[33:53],'big'),constraint=None,decoder='9e-fallback-v1')]
 if to==ROUTER_278 and raw[:4].hex()=='a00597a0':
  if profile.get('profile')!='278-a005-v1' or not profile.get('code_hash') or not profile.get('implementation_code_hash'):raise ValueError('unversioned proxy profile')
  if len(raw)<196:raise ValueError('truncated 278 ABI')
  v=[int.from_bytes(raw[i:i+32],'big') for i in range(4,196,32)]
  if v[1]>MASK160 or v[2]>MASK160 or v[3] not in (0,1) or v[4]>MASK160:raise ValueError('noncanonical 278 ABI')
  return [dict(kind='swap',pool='0x'+v[4].to_bytes(20,'big').hex(),zero=bool(v[3]),
      amount=v[0]-(1<<256) if v[0]>>255 else v[0],limit=v[1],constraint=None,decoder='278-a005-v1')]
 if to==ROUTER_C33 and raw[:4]==bytes.fromhex('000000e7'):
  if profile.get('profile')!='c33-e7-v1' or not profile.get('code_hash'):raise ValueError('unversioned custom profile')
  if len(raw)<164:raise ValueError('truncated custom ABI')
  v=[int.from_bytes(raw[i:i+32],'big') for i in range(4,164,32)]
  if v[0]>MASK160 or v[4]>MASK160 or v[1] not in (0,1) or v[3]>MASK160:raise ValueError('noncanonical custom ABI')
  return [dict(kind='swap',pool='0x'+v[0].to_bytes(20,'big').hex(),zero=bool(v[1]),amount=v[2]-(1<<256) if v[2]>>255 else v[2],limit=v[3],constraint=None,decoder='c33-e7-v1',payment_token='0x'+v[4].to_bytes(20,'big').hex())]
 if to!=ROUTER_520 or raw[:4]!=bytes.fromhex('b2460c48'):raise ValueError('packed selector not verified')
 if len(raw)<36:raise ValueError('truncated packed word')
 if profile.get('profile')!='520-b246-v1' or not profile.get('code_hash'):raise ValueError('unversioned packed profile')
 w=int.from_bytes(raw[4:36],'big');index=w>>240;exponent=(w>>232)&255;mantissa=(w>>168)&((1<<64)-1)
 pool=profile['pool_indexes'].get(str(index))
 if not pool:raise ValueError('unknown packed pool index '+str(index))
 amount=(mantissa<<exponent)&MASK256
 if amount>>255:amount-=1<<256
 return [dict(kind='swap',pool=pool,zero=bool(w&1),amount=amount,limit=(w>>8)&MASK160,constraint=None,
              decoder='520-b246-v1',pool_index=index,amount_mantissa=mantissa,amount_exponent=exponent)]

def inspect_29(calldata):
 """Parse routing intents only. Guards, vault balances and trailing constraint
 are not resolved: these records must NEVER be treated as executable swaps.
 """
 raw=bytes.fromhex(calldata[2:]) if isinstance(calldata,str) else calldata
 if raw[:4].hex() not in ('9c909e3f','e22092ea','164cb8f5'):raise ValueError('unverified 29 selector')
 d=raw[4:]
 if not d or len(d)%55:raise ValueError('packed record length')
 out=[]
 for i in range(0,len(d),55):
  r=d[i:i+55];flags=r[2]
  out.append(dict(pool_index=int.from_bytes(r[:2],'big'),flags=flags,zero=bool(flags&1),exact_output=bool(flags&2),balance_cap=bool(flags&4),requested_amount=int.from_bytes(r[3:19],'big'),limit=int.from_bytes(r[19:39],'big'),unresolved_constraint=int.from_bytes(r[39:55],'big'),executable=False))
 return out
