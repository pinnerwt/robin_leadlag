"""Observed three deferred fe transfers; token side effects remain unmodeled."""
from router0480_guards import inspect

def intents(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'));p=inspect(calldata);offsets=p['offsets'];start=len(p['guards'])+3;result=[];end=2+2*raw[0]
 if len(offsets)!=start+4:raise ValueError('unverified payment sequence')
 for i in range(start,start+3):
  result.append(one(calldata,i))
 return result

def one(calldata,index):
 raw=bytes.fromhex(calldata.removeprefix('0x'));p=inspect(calldata);offsets=p['offsets'];end=2+2*raw[0];i=index
 if not 0<=i<len(offsets)-1:raise ValueError('invalid payment index')
 c=raw[offsets[i]:offsets[i+1]]
 if len(c)!=7 or c[0]!=254:raise ValueError('unverified deferred payment')
 tokenoff,amountoff,recipientoff=[int.from_bytes(c[j:j+2],'big') for j in (1,3,5)]
 for pos,width in ((tokenoff,20),(amountoff,16),(recipientoff,20)):
  if not end<=pos<=offsets[0]-width:raise ValueError('payment operand bounds')
 token='0x'+raw[tokenoff:tokenoff+20].hex();recipient='0x'+raw[recipientoff:recipientoff+20].hex();amount=int.from_bytes(raw[amountoff:amountoff+16],'big')
 data='0xa9059cbb'+int(recipient,16).to_bytes(32,'big').hex()+amount.to_bytes(32,'big').hex()
 return dict(token=token,recipient=recipient,amount=amount,data=data,execution_complete=False)
