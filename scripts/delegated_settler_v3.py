"""Observed 8d68a156 single-hop full-balance intent; no I/O or state mutation."""
def intent(action,balance,pools):
 raw=bytes.fromhex(action.removeprefix('0x'))
 if raw[:4].hex()!='8d68a156':raise ValueError('settler V3 action selector')
 d=raw[4:]
 if len(d)!=224:raise ValueError('unverified V3 action size')
 words=[int.from_bytes(d[i:i+32],'big') for i in range(0,160,32)]
 if words[0]>=1<<160 or words[1:]!=[1000000,128,0,64]:raise ValueError('unverified V3 action layout/fraction')
 path=d[160:];token_in='0x'+path[:20].hex();token_out='0x'+path[44:].hex()
 # Observed four-byte path field. Do not generalize factory selection bits.
 profile=int.from_bytes(path[20:24],'big')
 spacing={100:1,500:10}.get(profile)
 if spacing is None:raise ValueError('unverified V3 pool profile')
 if type(balance) is not int or not 1<balance<1<<255:raise ValueError('insufficient or invalid balance')
 matches=[p for p in pools if p['tokens']==sorted([token_in,token_out]) and int(p['fee'])==profile and int(p['spacing'])==spacing]
 if len(matches)!=1:raise ValueError('missing or ambiguous verified pool')
 return dict(pool=matches[0]['pool'],recipient='0x'+words[0].to_bytes(20,'big').hex(),zero=token_in<token_out,
  amount=balance-1,limit=int.from_bytes(path[24:44],'big'),token_in=token_in,token_out=token_out,
  assumptions=['full balance credit','observed one-wei balance reservation'],execution_complete=False)
