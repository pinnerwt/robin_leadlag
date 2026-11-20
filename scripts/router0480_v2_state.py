"""Observed pair's 30bps swap invariant and reserve/TWAP transition, offline."""
MAX256=(1<<256)-1
MAX112=(1<<112)-1
def transition(storage,outputs,balances,timestamp):
 if len(outputs)!=2 or len(balances)!=2 or any(type(v) is not int or v<0 or v>MAX256 for v in (*outputs,*balances)) or type(timestamp) is not int or timestamp<0:raise ValueError('invalid V2 values')
 def slot(k):
  if k not in storage:raise ValueError('missing V2 slot '+k)
  return int(storage[k],16)
 if slot('0xc')!=1:raise ValueError('V2 locked')
 packed=slot('0x8');reserves=[packed&MAX112,(packed>>112)&MAX112]
 if not any(outputs) or any(o>=r for o,r in zip(outputs,reserves)):raise ValueError('V2 output liquidity')
 if any(b>MAX112 for b in balances):raise ValueError('V2 reserve overflow')
 inputs=[max(b-(r-o),0) for b,r,o in zip(balances,reserves,outputs)]
 if not any(inputs):raise ValueError('V2 missing input')
 adjusted=[b*1000-a*3 for b,a in zip(balances,inputs)]
 if any(v<0 for v in adjusted) or adjusted[0]*adjusted[1]<reserves[0]*reserves[1]*1000000:raise ValueError('V2 invariant')
 now=timestamp&((1<<32)-1);elapsed=(now-(packed>>224))&((1<<32)-1);writes={}
 if elapsed and all(reserves):
  writes['0x9']=hex((slot('0x9')+((reserves[1]<<112)//reserves[0])*elapsed)&MAX256)
  writes['0xa']=hex((slot('0xa')+((reserves[0]<<112)//reserves[1])*elapsed)&MAX256)
 writes['0x8']=hex(balances[0]+(balances[1]<<112)+(now<<224));writes['0xc']='0x1'
 return dict(inputs=inputs,reserves=balances.copy(),writes=writes,execution_complete=False)
