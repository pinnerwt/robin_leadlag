"""Strict observed three-guard, three-swap, reverse-payment route composition."""
from router0480_guards import inspect as guards
from router0480_first_swap import intent
from router0480_payments import intents as payments
from router0480_profit import condition

def inspect(calldata):
 p=guards(calldata)
 if len(p['guards'])!=3 or p['remaining_opcodes'] not in ([3,3,3,254,254,254,163],[3,4,4,254,254,254,163]):raise ValueError('unverified full route sequence')
 swaps=[intent(calldata,i) for i in (3,4,5)];pay=payments(calldata);terminal=condition(calldata)
 if len({s['pool'] for s in swaps})!=3:raise ValueError('repeated pool unsupported')
 for g,s in zip(p['guards'],reversed(swaps)):
  if g['pool']!=s['pool']:raise ValueError('guard pool order mismatch')
 for s,t in zip(reversed(swaps),pay):
  if (s['pool'],s['token_in'],s['amount'])!=(t['recipient'],t['token'],t['amount']):raise ValueError('deferred payment mismatch')
 # The first flash swap lends the terminal token; the other two restore inputs.
 if swaps[0]['token_out']!=swaps[2]['token_in'] or swaps[2]['token_out']!=swaps[1]['token_in'] or swaps[1]['token_out']!=swaps[0]['token_in']:raise ValueError('three-pool token cycle mismatch')
 if terminal['token']!=swaps[0]['token_out']:raise ValueError('terminal inventory token mismatch')
 return dict(guards=p['guards'],swaps=swaps,payments=pay,terminal=terminal,pools=[s['pool'] for s in swaps],scope_verified=False,execution_complete=False,unresolved=['router/pool/token code identity','pool callback registration','curve state and inventories','token side effects','continuous lifecycle'])
