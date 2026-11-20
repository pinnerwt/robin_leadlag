"""Observed empty-permit c1fb425e funding action. No swap/authorization claim."""
def inspect(calldata,owner):
 raw=bytes.fromhex(calldata.removeprefix('0x'))
 if raw[:4].hex()!='c1fb425e' or len(raw)!=228:raise ValueError('funding action layout')
 d=raw[4:];w=[int.from_bytes(d[i:i+32],'big') for i in range(0,len(d),32)]
 if any(x>=1<<160 for x in w[:2]) or w[3]!=0 or w[5:]!=[192,0]:raise ValueError('unsupported funding permit/profile')
 if not 0<w[2]<1<<256:raise ValueError('funding amount')
 owner_int=int(owner,16)
 if not 0<=owner_int<1<<160:raise ValueError('owner bounds')
 args=[w[1],owner_int,w[0],w[2]]
 return dict(recipient='0x'+w[0].to_bytes(20,'big').hex(),token='0x'+w[1].to_bytes(20,'big').hex(),amount=w[2],deadline=w[4],
  holder_transfer='0x15dacbea'+''.join(v.to_bytes(32,'big').hex() for v in args),execution_complete=False)
