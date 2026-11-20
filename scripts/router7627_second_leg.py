"""Observed native->USDG V4 delta feeds recorded V3 exact-input swap."""
ROUTER='0x762750e704f33d864289ce3c242fb559bf9b02ee'
POOL='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
LIMIT=1461446703485210103287273052203988822378723970341

def intent(v4_return):
 raw=bytes.fromhex(v4_return.removeprefix('0x'))
 if len(raw)!=32:raise ValueError('unverified V4 return layout')
 native=int.from_bytes(raw[:16],'big',signed=True);usdg=int.from_bytes(raw[16:],'big',signed=True)
 if native>=0 or usdg<=0:raise ValueError('unverified swap delta direction')
 values=[int(ROUTER,16),0,usdg,LIMIT,160,0]
 return dict(pool=POOL,zero=False,amount=usdg,native_input=-native,limit=LIMIT,data='0x128acb08'+b''.join(v.to_bytes(32,'big') for v in values).hex(),execution_complete=False)
