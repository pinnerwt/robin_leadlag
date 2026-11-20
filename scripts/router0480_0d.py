"""Observed native/USDG0d packed manager swap, actual callback validated."""
from router0480_extended_guards import MANAGER,AC_MAX

def intent(calldata,offset,stop):
 raw=bytes.fromhex(calldata.removeprefix('0x'));c=raw[offset:stop];end=2+2*raw[0];first=int.from_bytes(raw[2:4],'big')
 if len(c)!=76 or c[:2]!=b'\x0d\x00':raise ValueError('unverified0d profile')
 pointers=[int.from_bytes(c[i:i+2],'big') for i in (2,4,6,8,10)]
 for p,width in zip(pointers,(20,20,20,16,16)):
  if not end<=p<=first-width:raise ValueError('0d operand bounds')
 address=lambda p:'0x'+raw[p:p+20].hex();manager,c0,c1,amountoff,auxoff=pointers;amount=int.from_bytes(raw[amountoff:amountoff+16],'big');aux=int.from_bytes(raw[auxoff:auxoff+16],'big');config=int.from_bytes(c[12:44],'big')
 if address(manager)!=MANAGER or int(address(c0),16)!=0 or int(address(c1),16)==0 or not 0<amount<1<<127:raise ValueError('unverified0d native input profile')
 packed=(AC_MAX<<160)|(amount<<32)|0x80000000;words=[0,int(address(c1),16),config,packed]
 return dict(manager=MANAGER,pool_id='0x'+c[44:76].hex(),currency0=address(c0),currency1=address(c1),config=config,amount=amount,auxiliary_amount=aux,minimum_output=aux,data='0x00000000'+b''.join(w.to_bytes(32,'big') for w in words).hex(),scope_verified=False,execution_complete=False,unresolved=['packed parameter semantics and pool math','remaining settlement operations'])


def withdrawal(plan,return_data):
 """Validate observed native-output delta and reproduce the withdrawal intent."""
 from router0480_first_swap import ROUTER
 raw=bytes.fromhex(return_data.removeprefix('0x'))
 if len(raw)!=64:raise ValueError('manager swap return must be64bytes')
 output_delta=int.from_bytes(raw[:16],'big',signed=True);input_delta=int.from_bytes(raw[16:32],'big',signed=True)
 if input_delta!=plan['amount'] or output_delta>=0:raise ValueError('unexpected swap deltas')
 output=-output_delta
 if output<plan['minimum_output']:raise ValueError('minimum output not met')
 data='0x3ccfd60b'+bytes(20).hex()+ROUTER[2:]+output.to_bytes(16,'big').hex()
 return dict(to=plan['manager'],data=data,value=0,amount=output,execution_complete=False)


def payment_calls(plan):
 """Observed balance snapshot then exact input-token transfer."""
 token=plan['currency1'];manager=plan['manager'];amount=plan['amount']
 return [dict(to=manager,data='0xf9b6a796'+int(token,16).to_bytes(32,'big').hex(),value=0),
         dict(to=token,data='0xa9059cbb'+int(manager,16).to_bytes(32,'big').hex()+amount.to_bytes(32,'big').hex(),value=0)]


def settlement_call(plan):
 return dict(to=plan['manager'],data='0x12e103f1'+int(plan['currency1'],16).to_bytes(32,'big').hex(),value=0)


def validate_settlement(plan,return_data):
 raw=bytes.fromhex(return_data.removeprefix('0x'))
 if len(raw)!=16 or int.from_bytes(raw,'big')!=plan['amount']:raise ValueError('settled credit does not match input')
 return int.from_bytes(raw,'big')
