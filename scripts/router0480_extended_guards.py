"""Observed b8/ac guard encodings, established with local bytecode probes."""
MANAGER='0x00000000000014aa86c5d3c41765bb24e11bd701'
AC_MIN=0x400065a8177fae27
AC_MAX=0xffff9a5889f795069a41a8a3

def decode(raw,offset,stop,end,data_end):
 c=raw[offset:stop];op=c[0]
 if (op,len(c)) not in ((184,6),(172,38)) or c[1] not in (0,1):raise ValueError('unverified extended guard profile')
 addressoff=int.from_bytes(c[2:4],'big');limitoff=int.from_bytes(c[-2:],'big');width=16 if op==184 else 12
 if not end<=addressoff<=data_end-20 or not end<=limitoff<=data_end-width:raise ValueError('extended guard operand bounds')
 address='0x'+raw[addressoff:addressoff+20].hex();limit=int.from_bytes(raw[limitoff:limitoff+width],'big')
 if int(address,16)==0 or not limit:raise ValueError('zero extended guard operand')
 result=dict(opcode=op,side=c[1],limit=limit,offset=offset,limit_offset=limitoff)
 if op==184:
  result.update(pool=address,getter='0x1e2eaeaf',getter_data='0x1e2eaeaf'+'00'*32,storage_slot=0,price_encoding='biased_exponent16_mantissa104')
 else:
  if address!=MANAGER or not AC_MIN<=limit<=AC_MAX:raise ValueError('unverified ac manager or price bounds')
  pool='0x'+c[4:36].hex();result.update(pool=pool,manager=address,getter='0x380eb4e0',getter_data='0x380eb4e0'+pool[2:],price_encoding='upper96')
 return result

def price_from_word(opcode,word):
 if type(word) is not int or not 0<=word<1<<256:raise ValueError('invalid getter word')
 if opcode==172:
  price=word>>160
  if not AC_MIN<=price<=AC_MAX:return None
  return price
 if opcode==184:
  if word&255:return None
  exponent=(word>>8)&0xffff
  if exponent&0x8000:exponent-=1<<16
  return (((exponent+0x8000)&0xffff)<<104)|((word>>24)&((1<<104)-1))
 raise ValueError('unsupported guard encoding')
