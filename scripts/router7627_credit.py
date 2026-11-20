"""Observed manager credit withdrawal; subsequent V3 payment remains pending."""
from router7627_second_leg import ROUTER
MANAGER='0x8366a39cc670b4001a1121b8f6a443a643e40951'
USDG='0x5fc5360d0400a0fd4f2af552add042d716f1d168'
NATIVE_SLOT='fa47c3fbc6da32693cc210992343a11434b43c80b13805a65ec6bb65ee9c8b53'
USDG_SLOT='3f484ce2460dfc29d5b7bb3c02a8996d56dcc3340cd90f6dac693fa44e4d4060'

def take_usdg(credit):
 if type(credit) is not int or not 0<credit<1<<127:raise ValueError('unverified positive credit')
 return dict(to=MANAGER,data='0x0b0d9c09'+b''.join(x.to_bytes(32,'big') for x in (int(USDG,16),int(ROUTER,16),credit)).hex(),value=0,execution_complete=False)


def repayment_calls(native_debt,usdg_owed):
 from router7627_second_leg import POOL
 if any(type(x) is not int or not 0<x<1<<127 for x in (native_debt,usdg_owed)):raise ValueError('unverified repayment amount')
 weth='0x0bd7d308f8e1639fab988df18a8011f41eacad73'
 return [dict(to=weth,data='0x2e1a7d4d'+native_debt.to_bytes(32,'big').hex(),value=0),
         dict(to=MANAGER,data='0xa5841194'+'00'*32,value=0),
         dict(to=MANAGER,data='0x11da60b4',value=native_debt),
         dict(to=USDG,data='0xa9059cbb'+int(POOL,16).to_bytes(32,'big').hex()+usdg_owed.to_bytes(32,'big').hex(),value=0)]


def take_native(credit):
 """Reverse route withdraws the actual positive native transient delta."""
 if type(credit) is not int or not 0<credit<1<<127:raise ValueError('unverified positive native credit')
 return dict(to=MANAGER,data='0x0b0d9c09'+b''.join(x.to_bytes(32,'big') for x in (0,int(ROUTER,16),credit)).hex(),value=0,execution_complete=False)


def wrap_native(credit):
 """Observed reverse route deposits the full native credit into WETH."""
 take_native(credit) # Same positive signed-delta domain.
 return dict(to='0x0bd7d308f8e1639fab988df18a8011f41eacad73',data='0xd0e30db0',value=credit,execution_complete=False)
