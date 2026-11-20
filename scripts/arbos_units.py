"""Offline Nitro calldata-unit accounting, version-pinned research implementation.
Source: OffchainLabs/nitro ccc5c828d9ea22f161efc784bac4d4a6559b7e59.
No networking, no log-derived values. This does not implement all ArbOS hooks.
"""
import ctypes,ctypes.util
ARBOS='0xa4b05fffffffffffffffffffffffffffffffffff'
UNITS='0xa9f6f085d78d1d37c5819e5c16c9e03198bd14e08cd1f6f8191bc6207b9e9706'
ROOT='0x15fed0451499512d95f3ec5a41c878b9de55f21878b5b4e190d4667ec709b4'
_lib=ctypes.CDLL(ctypes.util.find_library('brotlienc'))
_compress=_lib.BrotliEncoderCompress
_compress.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_size_t,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.c_void_p]
_compress.restype=ctypes.c_int

def compressed_length(raw,quality):
 if not 0<=quality<=11:raise ValueError('invalid Brotli quality')
 size=ctypes.c_size_t(len(raw)+(len(raw)>>10)*8+64);out=ctypes.create_string_buffer(size.value)
 if not _compress(quality,22,0,len(raw),raw,ctypes.byref(size),out):raise ValueError('Brotli failure')
 return size.value

def rlp(v):
 if isinstance(v,int):
  if v<0:raise ValueError('negative RLP integer')
  v=v.to_bytes((v.bit_length()+7)//8,'big')
 if isinstance(v,list):raw=b''.join(rlp(x) for x in v);base=192
 else:
  raw=v;base=128
  if len(raw)==1 and raw[0]<128:return raw
 if len(raw)<56:return bytes([base+len(raw)])+raw
 n=len(raw).to_bytes((len(raw).bit_length()+7)//8,'big');return bytes([base+55+len(n)])+n+raw

def signed_units(raw,quality):
 """Signed standard L2 transaction, sequencer poster. No estimation padding."""
 return min((1<<64)-1,16*compressed_length(raw,quality))

def probe_units(call,quality):
 """debug_traceCall / eth_call fake-transaction branch, not signed live feed.
 Restricted to the empty access list, omitted nonce/fee fields used by our probes.
 """
 if any(k in call for k in ('nonce','gasPrice','maxFeePerGas','maxPriorityFeePerGas','accessList')):raise ValueError('unsupported probe context')
 data=bytes.fromhex(call['data'][2:]);to=bytes.fromhex(call['to'][2:]) if call.get('to') else b''
 fake=b'\x02'+rlp([0,0xa844cbcad86eb849,0x39ba7d26,0xf1aa387f,int(call['gas'],16),to,int(call.get('value','0x0'),16),data,[],42161*3,int('ef22bddd350b943170a67d35191c27e310709a28c38b5762a152ff640108f5b2',16),int('a9463b19d1148abedba3d6925530d4465b271ce2cc61f80b1a0a80fd73eab881',16)])
 return (signed_units(fake,quality)+256)*10100//10000

def checkpoint_parameters(seed):
 slots={hex(int(k,16)):int(v,16) for k,v in seed['accounts'][ARBOS]['storage'].items()}
 version=slots[ROOT+'00'];quality=slots[ROOT+'07']
 if version!=61:raise ValueError('unverified ArbOS version '+str(version))
 return slots[UNITS],quality
