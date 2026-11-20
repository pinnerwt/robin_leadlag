"""Atomic offline two-V3 action preview with explicit checkpoint inventories."""
from copy import deepcopy
from settler_funded_v3 import intent as funded
from delegated_settler_v3 import intent as balance_swap

def preview(first_action,next_action,*,upstream,downstream,pools,anchors,weth_balance):
 if set(anchors)!= {'upstream','downstream','inventory'} or len(set(anchors.values()))!=1 or not all(anchors.values()):raise ValueError('bridge anchor mismatch')
 if type(weth_balance) is not int or not 0<=weth_balance<1<<256:raise ValueError('invalid inventory')
 first=funded(first_action,pools);a=deepcopy(upstream);b=deepcopy(downstream)
 if (a.fee,a.spacing)!=(10000,200):raise ValueError('upstream curve profile')
 fill=a.swap(first['zero'],first['amount'],first['limit'],commit=True)
 if fill['unfilled']:raise ValueError('partial upstream fill')
 credit=-fill['amount1' if first['zero'] else 'amount0'];available=weth_balance+credit
 if available>=1<<256:raise ValueError('bridge inventory overflow')
 next_leg=balance_swap(next_action,available,pools)
 if next_leg['token_in']!=first['token_out'] or next_leg['pool']==first['pool']:raise ValueError('bridge token/pool mismatch')
 meta=next(p for p in pools if p['pool']==next_leg['pool'])
 if (b.fee,b.spacing)!=(int(meta['fee']),int(meta['spacing'])):raise ValueError('downstream curve profile')
 final=b.swap(next_leg['zero'],next_leg['amount'],next_leg['limit'],commit=True)
 if final['unfilled']:raise ValueError('partial downstream fill')
 return dict(upstream=a,downstream=b,upstream_fill=fill,downstream_fill=final,first=first,next=next_leg,weth_balance=available-next_leg['amount'],execution_complete=False,assumptions=['successful transaction','full token credit','explicit starting inventory','matching pool curve identity supplied by initializer'])
