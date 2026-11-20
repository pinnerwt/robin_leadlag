"""Observed opcode02 fixed-output V2 call; prefunding is a separate command."""
ROUTER='0x0480bafac5547926e8697de90d124b97d4a13f75'
def intent(calldata,offset,stop):
 raw=bytes.fromhex(calldata.removeprefix('0x'));c=raw[offset:stop]
 if len(c)!=8 or c[0]!=2 or c[1] not in (0,1):raise ValueError('unverified V2 command')
 pooloff,amountoff,recipientoff=[int.from_bytes(c[i:i+2],'big') for i in (2,4,6)]
 for p,n in ((pooloff,20),(amountoff,16)):
  if not 2+2*raw[0]<=p<=offset-n:raise ValueError('V2 pointer bounds')
 if recipientoff!=0:raise ValueError('unverified V2 recipient profile')
 amount=int.from_bytes(raw[amountoff:amountoff+16],'big')
 if not amount:raise ValueError('zero V2 output')
 amounts=[0,amount] if c[1] else [amount,0]
 data='0x022c0d9f'+b''.join(x.to_bytes(32,'big') for x in [*amounts,int(ROUTER,16),128,0]).hex()
 return dict(pool='0x'+raw[pooloff:pooloff+20].hex(),amount0_out=amounts[0],amount1_out=amounts[1],recipient=ROUTER,data=data,input_source='preceding explicit token transfer',execution_complete=False)
