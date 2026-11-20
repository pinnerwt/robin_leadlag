"""Observed two-pool0a/03 routes with explicit Arbitrum block equality."""
from router0480_guards import inspect as guards
from router0480_first_swap import intent as v3
from router0480_other_swaps import intent as other
from router0480_block_guard import decode as block_guard
from router0480_payments import one as payment
from router0480_profit import condition

def inspect(calldata):
 p=guards(calldata);o=p['offsets'];raw=bytes.fromhex(calldata.removeprefix('0x'))
 if len(p['guards'])!=2 or p['remaining_opcodes'] not in ([194,3,10,254,163],[194,10,3,254,163]):raise ValueError('unverified two-pool sequence')
 if sorted(g['opcode'] for g in p['guards'])!=[161,184]:raise ValueError('unverified two-pool guards')
 block=block_guard(raw,o[2],o[3],2+2*raw[0],o[0]);swaps=[v3(calldata,i) if raw[o[i]]==3 else other(calldata,o[i],o[i+1]) for i in (3,4)];pay=payment(calldata,5);terminal=condition(calldata);first,last=swaps
 if first['pool']==last['pool'] or [g['pool'] for g in p['guards']]!=[last['pool'],first['pool']]:raise ValueError('two-pool guard identity mismatch')
 if (first['token_in'],first['token_out'])!=(last['token_out'],last['token_in']):raise ValueError('two-pool currency cycle mismatch')
 for g in p['guards']:
  expected=next(s for s in swaps if s['pool']==g['pool'])
  if (g['opcode']==161)!=('swap_opcode' in expected):raise ValueError('guard type/pool mismatch')
 v=next(s for s in swaps if 'swap_opcode' in s)
 if (pay['recipient'],pay['token'],pay['amount'])!=(v['pool'],v['token_in'],v['amount']):raise ValueError('V3 deferred payment mismatch')
 if terminal['token']!=first['token_out']:raise ValueError('two-pool terminal currency mismatch')
 return dict(guards=p['guards'],block_guard=block,swaps=swaps,payments=[pay],terminal=terminal,pools=[s['pool'] for s in swaps],scope_verified=False,execution_complete=False,unresolved=['0a pool curve and callback settlement','token side effects and code identity','continuous lifecycle'])
