"""Research single-route modes0/128. Decode only; no execution/state validity claim."""
from delegated_compressed import Cursor,action

def expanded_condition(c):
 start=c.pos;flag=c.byte();prefix=c.take(8) if flag&128 else b'';records=[]
 for _ in range(flag&127):
  header=c.take(6)
  if header[0]>8:raise ValueError('condition argument size')
  target='0x'+c.take(20).hex();call=c.take(4+header[0]*32);value=int.from_bytes(c.take(32),'big')
  extra=c.take(8) if header[5]==3 else b''
  records.append(dict(header=header.hex(),target=target,calldata='0x'+call.hex(),value=value,extra=extra.hex()))
 return dict(flag=flag,prefix=prefix.hex(),records=records,expanded='0x'+c.data[start:c.pos].hex())

def inspect(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'));c=Cursor(raw)
 if c.take(4).hex()!='0c89e77a':raise ValueError('single route selector')
 mode=c.byte()
 if mode not in (0,128):raise ValueError('single route mode')
 condition=expanded_condition(c) if mode&128 else None
 count=c.byte();addresses=['0x'+'00'*20]+['0x'+c.take(20).hex() for _ in range(count)]
 header=[c.uint() for _ in range(5)];count=c.byte()
 if not 0<count<=64:raise ValueError('single route action count')
 actions=[action(c,addresses) for _ in range(count)]
 if c.pos!=len(raw):raise ValueError('single route trailing data')
 return dict(mode=mode,condition=condition,addresses=addresses,header=header,actions=actions,execution_complete=False)
