"""Observed V3/V4/V3 with fixed native wrapping; structural scope only."""
from router0480_guards import inspect as guards
from router0480_first_swap import intent as v3
from router0480_v4 import intent as v4
from router0480_payments import one as payment
from router0480_profit import condition
WETH='0x0bd7d308f8e1639fab988df18a8011f41eacad73'

def wrap(calldata,offset,stop):
 raw=bytes.fromhex(calldata.removeprefix('0x'));c=raw[offset:stop]
 if len(c)!=3 or c[0]!=8:raise ValueError('unverified wrap command')
 p=int.from_bytes(c[1:],'big');first=int.from_bytes(raw[2:4],'big')
 if not 2+2*raw[0]<=p<=first-16:raise ValueError('wrap operand bounds')
 return dict(to=WETH,data='0xd0e30db0',value=int.from_bytes(raw[p:p+16],'big'))

def inspect(calldata):
 p=guards(calldata);o=p['offsets'];g=p['guards']
 if [x['opcode'] for x in g]!=[161,168,161] or p['remaining_opcodes']!=[3,6,3,8,254,254,163]:raise ValueError('unverified V4 route sequence')
 first,last=v3(calldata,3),v3(calldata,5);middle=v4(calldata,o[4],o[5]);w=wrap(calldata,o[6],o[7]);pay=[payment(calldata,i) for i in (7,8)];terminal=condition(calldata)
 if [g[0]['pool'],g[2]['pool']]!=[last['pool'],first['pool']] or (g[1]['manager'],g[1]['pool'])!=(middle['manager'],middle['pool_id']):raise ValueError('V4 route guard mismatch')
 if first['pool']==last['pool']:raise ValueError('repeated V3 pool unsupported')
 if first['token_in']!=WETH or first['token_out']!=last['token_in'] or last['token_out']!=middle['key']['currency1']:raise ValueError('V4 currency cycle mismatch')
 if w['value']!=first['amount']:raise ValueError('wrap/payment amount mismatch')
 for swap,transfer in ((last,pay[0]),(first,pay[1])):
  if (swap['pool'],swap['token_in'],swap['amount'])!=(transfer['recipient'],transfer['token'],transfer['amount']):raise ValueError('V4 route payment mismatch')
 if terminal['token']!=first['token_out']:raise ValueError('V4 route terminal token mismatch')
 return dict(guards=g,swaps=[first,middle,last],wrap=w,payments=pay,terminal=terminal,pools=[first['pool'],middle['pool_id'],last['pool']],scope_verified=False,execution_complete=False,unresolved=['V4 output requires local curve state','callback and token side effects','continuous lifecycle and code identity'])
