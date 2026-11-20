"""Raw batch composition for the observed funded-V3 bridge; no code-pin bypass."""
from delegated_batch_route import nested_plan,SETTLER,WETH,USDG
from settler_funded_v3 import intent as funded
from delegated_settler_v3 import intent as downstream
from delegated_settler_tail import intent as tail

def inspect(calldata,pools):
 outer,router,holder=nested_plan(calldata);actions=holder['actions']
 if [a['selector'] for a in actions]!=['0x3036d6a6','0x8d68a156','0x5f80abae']:raise ValueError('unverified funded bridge sequence')
 first=funded(actions[0]['data'],pools);last=downstream(actions[1]['data'],2,pools);end=tail(actions[2]['data'],0)
 if (first['token_in'],first['amount'])!=(router['token'],router['amount']):raise ValueError('funding amount/token mismatch')
 if first['recipient']!=SETTLER or last['recipient']!=SETTLER:raise ValueError('bridge recipient mismatch')
 if first['token_out']!=WETH or (last['token_in'],last['token_out'])!=(WETH,USDG) or end['token']!=USDG or holder['buy_token']!=USDG:raise ValueError('bridge currency mismatch')
 if first['pool']==last['pool']:raise ValueError('repeated pool unsupported')
 last.pop('amount');last['amount_source']='starting WETH inventory plus upstream output minus one';end.pop('amount');end.pop('remaining')
 return dict(outer=outer,router=router,holder=holder,upstream=first,downstream=last,tail=end,pools=[first['pool'],last['pool']],execution_complete=False,scope_verified=False,
  unresolved=['entry/router/token code identity and side effects','starting inventories','outer authorization','all intervening state updates'])
