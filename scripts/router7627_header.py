"""Observed nine-byte fallback entry; first four bytes are a deadline, not selector."""
def inspect(calldata):
 raw=bytes.fromhex(calldata.removeprefix('0x'))
 if len(raw)!=9 or raw[8]!=0:raise ValueError('unverified7627 entry profile')
 return dict(deadline=int.from_bytes(raw[:4],'big'),parameter=int.from_bytes(raw[4:8],'big'),mode=raw[8],execution_complete=False)

def expired(plan,timestamp):
 if type(timestamp) is not int or not 0<=timestamp<1<<256:raise ValueError('invalid chain timestamp')
 return timestamp>plan['deadline']
