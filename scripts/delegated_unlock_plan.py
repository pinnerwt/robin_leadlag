"""Inspect expanded manager unlock plans. Does not decode compressed calldata or choose routes."""
from v3_calldata import word,blob,address

def inspect(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'))
 if raw[:4].hex() not in ('48c89491','91dd7346'):raise ValueError('not unlock payload')
 d=raw[4:]
 if word(d,0)!=32:raise ValueError('unlock bytes offset')
 body=blob(d,32)
 if word(body,0)!=6 or word(body,2)!=128:raise ValueError('unverified unlock plan mode')
 start=128;count=word(body[start:],0);base=start+32
 if not 0<count<=64:raise ValueError('strategy count')
 conditions_offset=word(body,3)
 if conditions_offset%32 or conditions_offset<base+count*32 or conditions_offset+32>len(body):raise ValueError('conditions offset')
 strategies=[]
 for i in range(count):
  relative=word(body[base:],i)
  if relative<count*32 or relative%32:raise ValueError('strategy offset')
  strategy=blob(body,base+relative)
  offset=word(strategy,3);trailer=word(strategy,4)
  if offset!=160:raise ValueError('action offset')
  n=word(strategy[offset:],0);begin=offset+32
  if not 0<n<=64 or trailer!=begin+352*n:raise ValueError('action layout')
  if trailer+32>len(strategy):raise ValueError('truncated strategy trailer')
  actions=[]
  for j in range(n):
   record=strategy[begin+j*352:begin+(j+1)*352]
   fields=[word(record,k) for k in range(11)]
   for k in (1,3,4,5,6,9):
    if fields[k]>=1<<160:raise ValueError('action address bounds')
   actions.append(dict(kind=fields[0],target=address(fields[1]),direction=fields[2],
    token_in=address(fields[3]),token_out=address(fields[4]),currency0=address(fields[5]),currency1=address(fields[6]),
    fee=fields[7],spacing=fields[8],hook=address(fields[9]),reserved=fields[10]))
  strategies.append(dict(input_amount=word(strategy,0),field1=word(strategy,1),field2=word(strategy,2),actions=actions,trailer='0x'+strategy[trailer:].hex()))
 conditions=body[conditions_offset:];n=word(conditions,0)
 if n>64:raise ValueError('condition group count')
 groups=[]
 for i in range(n):
  relative=word(conditions[32:],i)
  if relative<n*32 or relative%32:raise ValueError('condition group offset')
  groups.append('0x'+blob(conditions,32+relative).hex())
 return dict(condition_groups=groups,mode=6,field1=word(body,1),strategies=strategies,conditions='0x'+body[conditions_offset:].hex(),execution_complete=False)
