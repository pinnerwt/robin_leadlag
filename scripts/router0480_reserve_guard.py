"""Observed a4 reserve ratio predicate; inputs are local pool reserves."""
def decode(raw,offset,stop,data_start,data_end):
 c=raw[offset:stop]
 if len(c)!=8 or c[0]!=164 or c[1] not in (0,1):raise ValueError('unverified reserve guard')
 ptr=[int.from_bytes(c[i:i+2],'big') for i in (2,4,6)]
 for p,n in zip(ptr,(20,16,16)):
  if not data_start<=p<=data_end-n:raise ValueError('reserve guard pointer bounds')
 a,b=[int.from_bytes(raw[p:p+16],'big') for p in ptr[1:]]
 if not a or not b:raise ValueError('zero reserve reference')
 return dict(opcode=164,pool='0x'+raw[ptr[0]:ptr[0]+20].hex(),side=c[1],reference0=a,reference1=b,getter='0x0902f1ac',offset=offset)
def failed(guard,reserves):
 if not isinstance(reserves,(tuple,list)) or len(reserves)!=2 or any(type(v) is not int or not 0<v<1<<128 for v in reserves):raise ValueError('invalid or missing reserves')
 left=guard['reference0']*reserves[1];right=guard['reference1']*reserves[0]
 return left<right if guard['side']==1 else left>right
