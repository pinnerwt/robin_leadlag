"""Provisional local mode6 orchestration for two guarded native-return cycles.
Economic/settlement checks remain unmodeled; candidate success is assumed.
No RPC/logs/hash/subprocess. Unsupported routes/read layouts remain errors.
"""
from delegated_sequence import preview as sequence
from delegated_spcx_cycle import preview as cycle
from routera3d_v4 import MANAGER,POOL_ID
V4_SLOT='a652248898f7392773fb86e84bf1ef4cf17b449600f2d309595c039285782ad8'

def read(state,record):
 h=bytes.fromhex(record['header'])
 if h[1:5]!=bytes([0,1,160,0]):raise ValueError('unverified local condition extraction')
 target,data=record['target'],record['calldata']
 if data=='0x3850c7bd':curve=state['curves'][target]
 elif target==MANAGER and data=='0x1e2eaeaf'+V4_SLOT:curve=state['curves'][POOL_ID]
 else:raise ValueError('unverified local condition getter')
 # Only low160 bits are requested by the guarded extraction profile.
 return curve.sqrt.to_bytes(32,'big')

def execute(state,strategy,index):
 result=cycle(strategy,state['curves'],hook_state=state['hook_state'],hook_config=state['hook_config'],block=state['block'])
 state['curves']=result.pop('curves');state['hook_state']=result['hook_state']
 state.setdefault('executed',[]).append(dict(index=index,**result))

def preview(calldata,state):
 result=sequence(calldata,state,read=read,execute=execute)
 result['candidate_success_assumed']=True
 return result
