"""Observed V3/0d/native-wrap route; structural identities, not curve execution."""
from router0480_guards import inspect as guards
from router0480_first_swap import intent as v3
from router0480_0d import intent as manager_swap
from router0480_v4_route import wrap,WETH
from router0480_payments import one as payment
from router0480_profit import condition

def inspect(calldata):
 p=guards(calldata);g=p['guards'];o=p['offsets']
 if [x['opcode'] for x in g]!=[172,161] or p['remaining_opcodes']!=[3,13,8,254,163]:raise ValueError('unverified0d route sequence')
 first=v3(calldata,2);second=manager_swap(calldata,o[3],o[4]);w=wrap(calldata,o[4],o[5]);pay=payment(calldata,5);terminal=condition(calldata)
 if (g[0]['manager'],g[0]['pool'],g[1]['pool'])!=(second['manager'],second['pool_id'],first['pool']):raise ValueError('0d guard identities mismatch')
 if first['token_in']!=WETH or first['token_out']!=second['currency1']:raise ValueError('0d currency cycle mismatch')
 if w['value']!=first['amount'] or second['auxiliary_amount']!=w['value']:raise ValueError('0d wrap reference mismatch')
 if (pay['recipient'],pay['token'],pay['amount'])!=(first['pool'],first['token_in'],first['amount']):raise ValueError('0d deferred payment mismatch')
 if terminal['token']!=first['token_out']:raise ValueError('0d terminal currency mismatch')
 return dict(guards=g,swaps=[first,second],wrap=w,payments=[pay],terminal=terminal,pools=[first['pool'],second['pool_id']],scope_verified=False,execution_complete=False,unresolved=['manager pool key binding and code identity','manager curve and settlement','token side effects and continuous lifecycle'])
