"""Observed52-byte opcode06 native/token V4 intent; settlement unresolved."""
def intent(calldata,offset,stop):
 raw=bytes.fromhex(calldata.removeprefix('0x'));c=raw[offset:stop]
 if len(c)!=52 or c[:2]!=b'\x06\x00' or c[50:]!=bytes(2):raise ValueError('unverified V4 command profile')
 ptr=[int.from_bytes(c[i:i+2],'big') for i in (2,4,6,8,16)]
 for p,n in zip(ptr,(20,16,20,20,20)):
  if not 2+2*raw[0]<=p<=offset-n:raise ValueError('V4 operand bounds')
 addr=lambda p:'0x'+raw[p:p+20].hex();manager,amountoff,c0,c1,hook=ptr;amount=int.from_bytes(raw[amountoff:amountoff+16],'big');fee=int.from_bytes(c[10:13],'big');spacing=int.from_bytes(c[13:16],'big',signed=True)
 key=dict(currency0=addr(c0),currency1=addr(c1),fee=fee,tick_spacing=spacing,hooks=addr(hook))
 if not amount or key['currency0']!='0x'+'00'*20 or key['hooks']!='0x'+'00'*20 or (fee,spacing)!=(2500,25):raise ValueError('unverified native V4 key')
 limit=1461446703485210103287273052203988822378723970341
 values=[int(key['currency0'],16),int(key['currency1'],16),fee,spacing,0,0,-amount,limit,288,0]
 data='0xf3cd914c'+b''.join((x%(1<<256)).to_bytes(32,'big') for x in values).hex()
 return dict(manager=addr(manager),pool_id='0x'+c[18:50].hex(),key=key,zero=False,amount=-amount,limit=limit,data=data,execution_complete=False,scope_verified=False)
