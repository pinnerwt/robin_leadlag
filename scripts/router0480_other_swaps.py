"""Observed0a swap call, including full callback payload; curve unverified."""
from router0480_first_swap import ROUTER

def intent(calldata,offset,stop):
 raw=bytes.fromhex(calldata.removeprefix('0x'));c=raw[offset:stop];end=2+2*raw[0];first=int.from_bytes(raw[2:4],'big')
 if len(c)!=12 or c[0]!=10 or c[1] not in (0,1) or c[6:8]!=bytes(2):raise ValueError('unverified0a profile')
 pointers=[int.from_bytes(c[i:i+2],'big') for i in (2,4,8,10)]
 for p,n in zip(pointers,(20,16,20,20)):
  if not end<=p<=first-n:raise ValueError('0a operand bounds')
 pool,amountoff,t0,t1=pointers;amount=int.from_bytes(raw[amountoff:amountoff+16],'big');zero=bool(c[1]);addr=lambda p:'0x'+raw[p:p+20].hex()
 if not amount:raise ValueError('zero0a amount unsupported')
 limit=0 if zero else (1<<128)-1;offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(raw[0])];forward=bytearray(raw);forward[1]=offsets.index(offset)+1;callback=c[2:6]+c[8:12]+c[1:2]+forward;tail=len(callback).to_bytes(32,'big')+callback+bytes((-len(callback))%32);values=[int(ROUTER,16),int(zero),amount,limit,192,192+len(tail)]
 data='0xe24f0884'+(b''.join(x.to_bytes(32,'big') for x in values)+tail+bytes(32)).hex()
 return dict(pool=addr(pool),zero=zero,amount=amount,limit=limit,token_in=addr(t0 if zero else t1),token_out=addr(t1 if zero else t0),data=data,callback=callback.hex(),execution_complete=False,scope_verified=False)
