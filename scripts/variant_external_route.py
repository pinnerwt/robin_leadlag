"""Observed funding/external-native/wrap/V3 batch route, structural only."""
from delegated_batch_route import nested_plan,ROUTER,SETTLER,WETH,USDG
from settler_funding_action import inspect as funding
from settler_external_action import intent as external
from delegated_settler_v3 import intent as downstream
from delegated_settler_tail import intent as tail
TARGET='0xe3f09600259aebafc83e95901c67821587e8857e'

def inspect(calldata,pools):
 outer,router,holder=nested_plan(calldata);actions=holder['actions']
 if [a['selector'] for a in actions]!=['0xc1fb425e','0x38c9c147','0x38c9c147','0x8d68a156','0x5f80abae']:raise ValueError('external bridge action sequence')
 first=funding(actions[0]['data'],ROUTER);middle=external(actions[1]['data'],2)
 if (first['token'],first['amount'],first['recipient'])!=(router['token'],router['amount'],SETTLER):raise ValueError('external funding mismatch')
 payload=bytes.fromhex(middle['data'][2:])
 if middle['token']!=first['token'] or middle['target']!=TARGET or int.from_bytes(payload[68:100],'big')!=int(SETTLER,16):raise ValueError('external target/token/recipient mismatch')
 word=lambda x:x.to_bytes(32,'big')
 expected=bytes.fromhex('38c9c147')+b''.join(word(x) for x in [int('ee'*20,16),1000000,int(WETH,16),4,160,36])+bytes.fromhex('d0e30db0')+bytes(60)
 if bytes.fromhex(actions[2]['data'][2:])!=expected:raise ValueError('external wrap mismatch')
 last=downstream(actions[3]['data'],2,pools);end=tail(actions[4]['data'],0)
 if (last['token_in'],last['token_out'],last['recipient'],end['token'],holder['buy_token'])!=(WETH,USDG,SETTLER,USDG,USDG):raise ValueError('external downstream currencies')
 middle.pop('amount');middle.pop('data');middle['amount_source']='starting input inventory plus funding amount minus one';last.pop('amount');last['amount_source']='starting WETH plus native inventory plus external output minus one';end.pop('amount');end.pop('remaining')
 return dict(outer=outer,router=router,holder=holder,funding=first,external=middle,downstream=last,tail=end,pools=[last['pool']],scope_verified=False,execution_complete=False,unresolved=['entry/code identity and token side effects','external curve lifecycle','starting inventories','whole transaction success'])
