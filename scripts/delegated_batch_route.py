"""Observed batch/router/holder/settler calldata composition, not live dispatch.
Code identities, opaque auth fields and token side effects require external
validation. Never treat successful parsing as proof of exclusive pool scope.
"""
from delegated_batch_envelope import inspect as envelope
from delegated_holder_plan import inspect as holder
from delegated_settler_v4 import first_swap
from delegated_settler_v3 import intent as v3_intent
from delegated_settler_tail import intent as tail_intent
ROUTER='0x5399d94d2cab7c252a6034042e1917a0e5e17a18'
HOLDER='0x0000000000001ff3684f28c67538d4d072c22734'
SETTLER='0xe8852602f84e04e284286d8db01a41edd0ccefb0'
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
USDG='0x5fc5360d0400a0fd4f2af552add042d716f1d168'

def router_payload(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'));d=raw[4:]
 if raw[:4].hex()!='0a54da07' or len(d)<288:raise ValueError('router layout')
 w=[int.from_bytes(d[i:i+32],'big') for i in range(0,288,32)]
 if w[6]!=288 or any(w[i]>=1<<160 for i in (1,5,7)):raise ValueError('router address/offset')
 def blob(offset):
  if offset<288 or offset+32>len(d) or offset%32:raise ValueError('router bytes offset')
  n=int.from_bytes(d[offset:offset+32],'big');end=offset+32+n;pad=offset+32+((n+31)//32)*32
  if pad>len(d) or any(d[end:pad]):raise ValueError('router bytes bounds/padding')
  return '0x'+d[offset+32:end].hex(),pad
 payload,end=blob(w[6])
 if w[8]!=end:raise ValueError('router signature offset')
 signature,end=blob(w[8])
 if end!=len(d):raise ValueError('router trailing bytes')
 addr=lambda x:'0x'+x.to_bytes(20,'big').hex()
 return dict(order_word=w[0],token=addr(w[1]),amount=w[2],minimum_word=w[3],deadline=w[4],holder=addr(w[5]),signer=addr(w[7]),signature=signature,payload=payload)

def nested_plan(calldata):
 outer=envelope(calldata)
 if len(outer['calls'])!=2:raise ValueError('unverified batch call count')
 approval,call=outer['calls']
 if call['target']!=ROUTER or call['value'] or approval['value']:raise ValueError('unverified batch target/value')
 route=router_payload(call['data']);p=holder(route['payload'])
 approve=bytes.fromhex(approval['data'][2:])
 if len(approve)!=68 or approve[:4].hex()!='095ea7b3':raise ValueError('approval layout')
 if approval['target']!=route['token'] or int.from_bytes(approve[4:36],'big')!=int(ROUTER,16) or int.from_bytes(approve[36:],'big')!=route['amount']:raise ValueError('approval mismatch')
 if route['holder']!=HOLDER or p['operator']!=SETTLER or p['target']!=SETTLER or p['recipient']!=ROUTER:raise ValueError('unverified nested target')
 if (p['token'],p['amount'])!=(route['token'],route['amount']):raise ValueError('holder input mismatch')
 return outer,route,p

def inspect(calldata,pools):
 outer,route,p=nested_plan(calldata)
 actions=p['actions']
 if [a['selector'] for a in actions]!=['0x6a92dacb','0x38c9c147','0x8d68a156','0x5f80abae']:raise ValueError('unverified action sequence')
 a=first_swap(actions[0]['data']);raw=bytes.fromhex(actions[0]['data'][10:])
 if int.from_bytes(raw[:32],'big')!=int(SETTLER,16) or a['currency0']!='0x'+'00'*20 or a['currency1']!=route['token'] or a['zero'] or a['amount']!=route['amount']:raise ValueError('upstream action mismatch')
 wrap=bytes.fromhex(actions[1]['data'][10:]);word=lambda x:x.to_bytes(32,'big')
 expected=b''.join(word(x) for x in [int('ee'*20,16),1000000,int(WETH,16),4,160,36])+bytes.fromhex('d0e30db0')+bytes(60)
 if wrap!=expected:raise ValueError('unverified full wrap action')
 v3=v3_intent(actions[2]['data'],2,pools);v3.pop('amount');v3['amount_source']='WETH balance minus one'
 tail=tail_intent(actions[3]['data'],0);tail.pop('amount');tail.pop('remaining')
 if v3['recipient']!=SETTLER or (v3['token_in'],v3['token_out'])!=(WETH,USDG) or tail['token']!=USDG or p['buy_token']!=USDG:raise ValueError('downstream token flow mismatch')
 return dict(outer=outer,router=route,holder=p,v4=a,v3=v3,tail=tail,execution_complete=False,scope_verified=False,
  unresolved=['code pins and authorization','hook branch/state','token side effects','outer post-call behavior'])
