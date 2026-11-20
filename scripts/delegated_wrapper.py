"""Research 31abd933 framing verified against saved delegatecall payload.
No authorization verification or claim that the four trailer words are optional.
"""
from delegated_single import inspect as single

def inspect(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'))
 if raw[:4].hex()!='31abd933' or len(raw)<4+5+128:raise ValueError('invalid delegated wrapper')
 inner=raw[4:-128]
 plan=single('0x'+inner.hex())
 return dict(inner_calldata='0x'+inner.hex(),trailer_words=[int.from_bytes(raw[i:i+32],'big') for i in range(len(raw)-128,len(raw),32)],plan=plan,
  authorization_verified=False,execution_complete=False)
