"""Observed single-hop 6a92dacb packed path -> V4 arguments, not fee/execution model."""
ZERO='0x'+'00'*20
NATIVE='0x'+'ee'*20

def first_swap(action):
 raw=bytes.fromhex(action.removeprefix('0x'))
 if raw[:4].hex()!='6a92dacb':raise ValueError('settler V4 action selector')
 d=raw[4:]
 def w(i):
  b=d[i*32:(i+1)*32]
  if len(b)!=32:raise ValueError('truncated action')
  return int.from_bytes(b,'big')
 if w(9)!=384 or w(10)!=512 or w(12)!=73 or len(d)!=544 or w(16)!=0:
  raise ValueError('unverified single-hop action layout')
 if any(d[489:512]):raise ValueError('nonzero path padding')
 path=d[416:489]
 if int.from_bytes(path[:3],'big')!=1000000 or path[23]!=1 or path[70:]!=bytes(3):
  raise ValueError('unverified path fraction/flags/hook data')
 if w(1)>=1<<160:raise ValueError('input currency overflow')
 token='0x'+w(1).to_bytes(20,'big').hex();out='0x'+path[24:44].hex()
 token=ZERO if token==NATIVE else token;out=ZERO if out==NATIVE else out
 if token==out:raise ValueError('identical currencies')
 amount=w(2)
 if not 0<amount<1<<127:raise ValueError('input amount bounds')
 c0,c1=sorted((token,out));zero=token==c0
 fee=int.from_bytes(path[44:47],'big');spacing=int.from_bytes(path[47:50],'big',signed=True)
 hook='0x'+path[50:70].hex();limit=int.from_bytes(path[3:23],'big')
 fields=[int(c0,16),int(c1,16),fee,spacing%(1<<256),int(hook,16),int(zero),(-amount)%(1<<256),limit,288,0]
 return dict(currency0=c0,currency1=c1,fee=fee,spacing=spacing,hook=hook,zero=zero,amount=amount,limit=limit,
  swap_calldata='0xf3cd914c'+''.join(x.to_bytes(32,'big').hex() for x in fields),
  execution_complete=False)
