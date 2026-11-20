"""Research raw-calldata preview; not a production reducer or hook updater."""
from router7627_header import inspect,expired
from router7627_price_gate import branch
from router7627_reverse_preview import preview
from router7627_second_leg import ROUTER
CODE_HASH='0xb567419b457e60dd8abc263fc5e102ec797cc23788f533149754404d23e17b6b'

def decode(to,calldata,timestamp,v3,v4,*,code_hash):
 if to.lower()!=ROUTER or code_hash.lower()!=CODE_HASH:raise ValueError('unverified router code profile')
 header=inspect(calldata)
 base=dict(header=header,execution_complete=False,state_applied=False)
 if expired(header,timestamp):return dict(base,status='no_swap',reason='expired',swaps=[])
 gate=branch(v3.sqrt,v4.sqrt)
 if gate['branch']==0:return dict(base,status='no_swap',reason='inside_price_band',swaps=[])
 if gate['branch']!=1:raise ValueError('forward optimizer not implemented')
 prediction=preview(v3,v4,None,header['parameter'])
 return dict(base,status='reverse_prediction',reason=None,prediction=prediction,
             swaps=[dict(venue='v3',data=prediction['v3_calldata']),dict(venue='v4',data=prediction['v4_calldata'])])
