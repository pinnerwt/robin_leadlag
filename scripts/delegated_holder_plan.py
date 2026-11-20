"""Strict observed holder/settler ABI framing; action semantics remain opaque."""
def inspect(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'))
 if raw[:4].hex()!='2213bc0b':raise ValueError('holder selector')
 d=raw[4:]
 def word(data,offset):
  if offset<0 or offset+32>len(data):raise ValueError('truncated word')
  return int.from_bytes(data[offset:offset+32],'big')
 def addr(data,offset):
  n=word(data,offset)
  if n>=1<<160:raise ValueError('address overflow')
  return '0x'+n.to_bytes(20,'big').hex()
 def blob(data,offset):
  n=word(data,offset);end=offset+32+n;pad=offset+32+((n+31)//32)*32
  if pad>len(data) or any(data[end:pad]):raise ValueError('bytes bounds/padding')
  return data[offset+32:end],pad
 if word(d,128)!=160:raise ValueError('holder bytes offset')
 inner,end=blob(d,160)
 if end!=len(d) or inner[:4].hex()!='1fff991f':raise ValueError('holder payload/trailer')
 b=inner[4:]
 if word(b,96)!=160:raise ValueError('settler action offset')
 count=word(b,160)
 if not 0<count<=64:raise ValueError('settler action count')
 base=192;cursor=base+count*32;actions=[]
 for i in range(count):
  offset=base+word(b,base+i*32)
  if offset!=cursor:raise ValueError('noncanonical action offset')
  action,cursor=blob(b,offset)
  if len(action)<4:raise ValueError('short action')
  actions.append(dict(selector='0x'+action[:4].hex(),data='0x'+action.hex()))
 if cursor!=len(b):raise ValueError('settler trailing bytes')
 return dict(operator=addr(d,0),token=addr(d,32),amount=word(d,64),target=addr(d,96),
  inner_calldata='0x'+inner.hex(),recipient=addr(b,0),buy_token=addr(b,32),min_output=word(b,64),
  opaque_word4='0x'+b[128:160].hex(),actions=actions,scope_verified=False,execution_complete=False)
