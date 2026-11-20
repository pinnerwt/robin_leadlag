"""Research mode6 compressed strategy parser. Strategy and condition decoding only; not a live swap decoder."""
class Cursor:
 def __init__(self,data):self.data=data;self.pos=0
 def take(self,n):
  if n<0 or self.pos+n>len(self.data):raise ValueError('truncated compressed plan')
  out=self.data[self.pos:self.pos+n];self.pos+=n;return out
 def byte(self):return self.take(1)[0]
 def uint(self):
  n=self.byte()
  if n>32:raise ValueError('integer width')
  return int.from_bytes(self.take(n),'big')

def condition_group(c,addresses):
 flag=c.byte();expanded=bytearray([flag]);records=[]
 prefix=c.take(8) if flag&128 else b'';expanded.extend(prefix)
 for _ in range(flag&127):
  header=c.take(7);words=header[0];index=header[6]
  if words>8 or index>=len(addresses):raise ValueError('condition address/argument size')
  target=addresses[index];call=c.take(4+32*words);value=c.uint()
  extra=c.take(8) if header[5]==3 else b''
  expanded.extend(header[:6]+bytes.fromhex(target[2:])+call+value.to_bytes(32,'big')+extra)
  records.append(dict(header=header[:6].hex(),target=target,calldata='0x'+call.hex(),value=value,extra=extra.hex()))
 return dict(flag=flag,prefix=prefix.hex(),records=records,expanded='0x'+expanded.hex())

def action(c,addresses):
 kind,flags,target,tokenin,tokenout,curr0,curr1,hook=c.take(8)
 if flags>7:raise ValueError('action flags')
 if max(target,tokenin,tokenout,curr0,curr1,hook)>=len(addresses):raise ValueError('address reference')
 fee=int.from_bytes(c.take(3),'big') if flags&2 else 0
 spacing=int.from_bytes(c.take(3),'big',signed=True) if flags&2 else 0
 reserved=c.uint() if flags&4 else 0
 return dict(kind=kind,target=addresses[target],direction=flags&1,token_in=addresses[tokenin],token_out=addresses[tokenout],currency0=addresses[curr0],currency1=addresses[curr1],fee=fee,spacing=spacing,hook=addresses[hook],reserved=reserved)

def inspect(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'));c=Cursor(raw)
 if c.take(4).hex()!='0c89e77a' or c.byte()!=6:raise ValueError('unverified compressed mode')
 n=c.byte();addresses=['0x'+'00'*20]+['0x'+c.take(20).hex() for _ in range(n)]
 header=[c.uint() for _ in range(4)]
 count=c.byte();conditions_mode=c.byte()
 if not 0<count<=64 or conditions_mode>2:raise ValueError('strategy/condition mode')
 strategies=[]
 for _ in range(count):
  amount,field1,field2=c.uint(),c.uint(),c.uint();actions=[];n=c.byte()
  if not 0<n<=64:raise ValueError('action count')
  for _ in range(n):
   actions.append(action(c,addresses))
  if c.byte()!=0:raise ValueError('strategy trailer not verified')
  strategies.append(dict(input_amount=amount,field1=field1,field2=field2,actions=actions,trailer='0x'+'00'*32))
 conditions_offset=c.pos;tail=raw[c.pos:];groups=None
 if conditions_mode==2:
  groups=[condition_group(c,addresses) for _ in range(count)]
  if c.pos!=len(raw):raise ValueError('trailing compressed conditions')
 return dict(mode=6,header=header,addresses=addresses,strategies=strategies,conditions_mode=conditions_mode,condition_groups=groups,conditions_offset=conditions_offset,compressed_conditions='0x'+tail.hex(),execution_complete=False)
