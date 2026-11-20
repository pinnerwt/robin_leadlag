"""Observed mode0 WETH threshold before native-debt repayment; research only."""
def required_balance(initial,native_debt,parameter):
 if any(type(x) is not int or x<0 for x in (initial,native_debt,parameter)) or parameter>=1<<32:raise ValueError('invalid threshold inputs')
 minimum=max(1,parameter*10**9//2);required=initial+native_debt+minimum
 if required>=1<<256:raise ValueError('balance overflow')
 return dict(minimum=minimum,required=required)


def payout(initial,final):
 if any(type(x) is not int or not 0<=x<1<<256 for x in (initial,final)) or final<=initial:raise ValueError('unverified positive payout')
 recipient='0xac6d42b13660fe34ffb1d79e54506530a7878418';amount=final-initial
 return dict(to='0x0bd7d308f8e1639fab988df18a8011f41eacad73',recipient=recipient,amount=amount,data='0xa9059cbb'+int(recipient,16).to_bytes(32,'big').hex()+amount.to_bytes(32,'big').hex(),execution_complete=False)
