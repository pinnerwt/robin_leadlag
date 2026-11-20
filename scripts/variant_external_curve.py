"""Observed e3f096 d04c6983 native-output curve; no I/O, explicit state branch."""
LIMIT=1<<256
GUARD='0x9b779b17422d0df92223018b32b4d1fa46e071723d6817e2486d003becc55f00'
def sell(storage,amount):
 def slot(k):
  if k not in storage:raise ValueError('missing curve slot '+k)
  x=int(storage[k],16)
  if not 0<=x<LIMIT:raise ValueError('invalid storage word')
  return x
 def checked(x):
  if not 0<=x<LIMIT:raise ValueError('curve arithmetic overflow/underflow')
  return x
 if type(amount) is not int or not 0<amount<LIMIT:raise ValueError('invalid amount')
 if slot('0x7')&255 or (slot('0x1')>>160)&255:raise ValueError('unsupported curve branch')
 if slot(GUARD)==2:raise ValueError('reentrant curve')
 reserve=slot('0x5');tokens=slot('0x6');a=slot('0x2');b=slot('0x4')
 virtual=checked(checked(checked(reserve+1680000000000000000)-a)-b)
 # Preserve the actual checked intermediate multiplications in bytecode.
 adjusted=checked(amount*10000);numerator=checked(adjusted*virtual)
 denominator=checked(checked(tokens*10000)+adjusted)
 gross=numerator//denominator;fee=checked(gross*100)//10000;output=checked(gross-fee-fee)
 writes={'0x2':hex(checked(a+fee)),'0x4':hex(checked(b+fee)),'0x5':hex(checked(reserve-output)),'0x6':hex(checked(tokens+amount)),GUARD:'0x1'}
 return dict(gross=gross,output=output,fee_each=fee,writes=writes,execution_complete=False)
