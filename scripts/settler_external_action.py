"""Observed ERC20 full-balance external action; target semantics remain unknown."""
def intent(calldata,balance):
 raw=bytes.fromhex(calldata.removeprefix('0x'));d=raw[4:]
 if raw[:4].hex()!='38c9c147' or len(d)!=320:raise ValueError('external action layout')
 w=[int.from_bytes(d[i:i+32],'big') for i in range(0,192,32)]
 if w[0]>=1<<160 or w[2]>=1<<160 or w[1]!=1000000 or w[3:6]!=[4,160,100]:raise ValueError('external action profile')
 payload=d[192:292]
 if any(d[292:]) or payload[:4].hex()!='d04c6983' or any(payload[4:68]) or int.from_bytes(payload[68:100],'big')>=1<<160:raise ValueError('external payload profile')
 if type(balance) is not int or not 1<balance<1<<256:raise ValueError('invalid balance')
 if w[0]==int('ee'*20,16):raise ValueError('native action unsupported')
 return dict(token='0x'+w[0].to_bytes(20,'big').hex(),target='0x'+w[2].to_bytes(20,'big').hex(),amount=balance-1,
  data='0x'+(payload[:4]+(balance-1).to_bytes(32,'big')+payload[36:]).hex(),execution_complete=False,scope_verified=False)
