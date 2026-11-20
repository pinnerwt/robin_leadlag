"""Observed 5f80abae full-surplus transfer intent; no token callback scope claim."""
def intent(action,balance):
 raw=bytes.fromhex(action.removeprefix('0x'))
 if raw[:4].hex()!='5f80abae' or len(raw)!=164:raise ValueError('tail action layout')
 d=raw[4:];w=[int.from_bytes(d[i:i+32],'big') for i in range(0,160,32)]
 if max(w[:2])>=1<<160 or w[3:]!=[1000000,1000000]:raise ValueError('unverified tail profile')
 if type(balance) is not int or not 0<=balance<1<<256:raise ValueError('balance bounds')
 # This profile consumes full positive surplus; other fractions need separate verification.
 amount=max(0,balance-1-w[2])
 return dict(recipient='0x'+w[0].to_bytes(20,'big').hex(),token='0x'+w[1].to_bytes(20,'big').hex(),
  threshold=w[2],amount=amount,remaining=balance-amount,execution_complete=False)
