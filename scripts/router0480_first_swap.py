"""Observed three opcode03 exact-input calls; callback accounting remains isolated."""
from router0480_guards import inspect
ROUTER='0x0480bafac5547926e8697de90d124b97d4a13f75'
def intent(calldata,command_index=None):
 raw=bytes.fromhex(calldata.removeprefix('0x'));plan=inspect(calldata);i=len(plan['guards']) if command_index is None else command_index;offsets=plan['offsets']
 if i not in (len(plan['guards']),len(plan['guards'])+1,len(plan['guards'])+2):raise ValueError('unverified command position')
 if i+1>=len(offsets):raise ValueError('missing first swap command')
 c=raw[offsets[i]:offsets[i+1]]
 if not c or (c[0],len(c)) not in ((3,14),(4,13)) or c[1] not in (0,1) or c[2]!=1 or (c[0]==3 and c[13] not in (0,1,5,30)) or c[7:9]!=bytes(2):raise ValueError('unverified swap opcode profile')
 pooloff=int.from_bytes(c[3:5],'big');amountoff=int.from_bytes(c[5:7],'big');inp=int.from_bytes(c[9:11],'big');out=int.from_bytes(c[11:13],'big');end=2+2*raw[0]
 for p,width in ((pooloff,20),(amountoff,16),(inp,20),(out,20)):
  if not end<=p<=offsets[0]-width:raise ValueError('swap operand out of data region')
 amount=int.from_bytes(raw[amountoff:amountoff+16],'big')
 if not amount:raise ValueError('zero amount unsupported')
 return dict(pool='0x'+raw[pooloff:pooloff+20].hex(),recipient=ROUTER,zero=bool(c[1]),amount=amount,limit=4295128740 if c[1] else 1461446703485210103287273052203988822378723970341,token_in='0x'+raw[inp:inp+20].hex() if c[1] else '0x'+raw[out:out+20].hex(),token_out='0x'+raw[out:out+20].hex() if c[1] else '0x'+raw[inp:inp+20].hex(),command_index=i,swap_opcode=c[0],callback_profile=c[13] if c[0]==3 else None,amount_offset=amountoff,callback_unresolved=True,scope_verified=False)
