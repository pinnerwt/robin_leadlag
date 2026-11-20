"""Observed 3036d6a6 empty-permit single-hop V3 funding action."""
def intent(calldata,pools):
 raw=bytes.fromhex(calldata.removeprefix('0x'));d=raw[4:]
 if raw[:4].hex()!='3036d6a6' or len(d)!=384:raise ValueError('funded V3 layout')
 w=[int.from_bytes(d[i:i+32],'big') for i in range(0,288,32)]
 if w[0]>=1<<160 or w[1]>=1<<160 or not 0<w[2]<1<<255 or w[3]!=0 or w[5:]!=[256,352,0,44] or any(d[332:]):raise ValueError('funded V3 profile')
 path=d[288:332]
 if path[:4]!=bytes.fromhex('00002710'):raise ValueError('funded V3 fee/factory profile')
 token_in='0x'+w[1].to_bytes(20,'big').hex();token_out='0x'+path[24:].hex()
 matches=[p for p in pools if p['tokens']==sorted([token_in,token_out]) and int(p['fee'])==10000 and int(p['spacing'])==200]
 if len(matches)!=1:raise ValueError('missing or ambiguous funded pool')
 return dict(pool=matches[0]['pool'],token_in=token_in,token_out=token_out,recipient='0x'+w[0].to_bytes(20,'big').hex(),amount=w[2],zero=token_in<token_out,limit=int.from_bytes(path[4:24],'big'),deadline=w[4],execution_complete=False)
