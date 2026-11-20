"""Observed two V3 calls then prefunded V2 output, structural composition only."""
from router0480_guards import inspect as guards
from router0480_first_swap import intent as v3
from router0480_v2 import intent as v2
from router0480_payments import one as payment
from router0480_profit import condition

def inspect(calldata,v2_pools):
 p=guards(calldata);offsets=p['offsets']
 if len(p['guards'])!=3 or p['remaining_opcodes']!=[3,3,254,2,254,254,163]:raise ValueError('unverified mixed command sequence')
 first,second=[v3(calldata,i) for i in (3,4)];pair=v2(calldata,offsets[6],offsets[7]);pay=[payment(calldata,i) for i in (5,7,8)];terminal=condition(calldata)
 if pair['pool'] not in v2_pools:raise ValueError('missing verified V2 token metadata')
 tokens=v2_pools[pair['pool']]['tokens']
 if len(tokens)!=2 or tokens[0]==tokens[1]:raise ValueError('invalid V2 metadata')
 output_index=1 if pair['amount1_out'] else 0;pair.update(token_out=tokens[output_index],token_in=tokens[1-output_index],input_amount=pay[0]['amount'])
 if (pay[0]['recipient'],pay[0]['token'])!=(pair['pool'],pair['token_in']):raise ValueError('V2 prefunding mismatch')
 for swap,transfer in ((second,pay[1]),(first,pay[2])):
  if (swap['pool'],swap['token_in'],swap['amount'])!=(transfer['recipient'],transfer['token'],transfer['amount']):raise ValueError('mixed deferred payment mismatch')
 if pair['token_in']!=first['token_out'] or pair['token_out']!=second['token_in'] or second['token_out']!=first['token_in']:raise ValueError('mixed currency cycle mismatch')
 if pair['amount0_out']+pair['amount1_out']!=second['amount']:raise ValueError('V2 output does not cover observed exact payment')
 pools=[first['pool'],second['pool'],pair['pool']]
 if len(set(pools))!=3 or [g['pool'] for g in p['guards']]!=list(reversed(pools)):raise ValueError('mixed pool/guard mismatch')
 if terminal['token']!=first['token_out']:raise ValueError('mixed terminal token')
 return dict(guards=p['guards'],swaps=[first,second,pair],payments=pay,terminal=terminal,pools=pools,scope_verified=False,execution_complete=False,unresolved=['code identity and callback registrations','all curve state and inventory','prefunded V2 invariant','token side effects','continuous lifecycle'])
