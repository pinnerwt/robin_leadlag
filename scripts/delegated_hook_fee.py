"""Verified native-output exact-input branch arithmetic for e5e702 hook.
Caller must validate code hash, direction, active pool configuration and branch.
This helper does not select branches or handle accounting writes/initialization.
"""
def native_output_fee(config_word,gross):
 if type(config_word) is not int or not 0<=config_word<1<<256:raise ValueError('configuration word bounds')
 if type(gross) is not int or not 0<=gross<1<<127:raise ValueError('gross output bounds')
 rate_a=(config_word>>160)&65535;rate_b=(config_word>>208)&65535
 if rate_a+rate_b>10000:raise ValueError('unsupported aggregate fee')
 component_a=gross*rate_a//10000;component_b=gross*rate_b//10000
 return dict(component_a=component_a,component_b=component_b,fee=component_a+component_b,
  net=gross-component_a-component_b,rate_a=rate_a,rate_b=rate_b)

def accounting_update(storage,config_word,gross,*,slot12,slot13):
 """Preview writes for the verified no-referral branch; slots precomputed at init.
 Mapping12 accrues component_b; mapping13 accrues component_a. Missing nonzero
 counters and uint256 overflow reject without mutating the supplied storage.
 """
 if slot12==slot13:raise ValueError('ambiguous fee accounting slots')
 fee=native_output_fee(config_word,gross);writes={}
 for slot,increment in ((slot12,fee['component_b']),(slot13,fee['component_a'])):
  if not increment:continue
  if slot not in storage:raise ValueError('missing fee accounting state '+slot)
  before=storage[slot]
  if type(before) is not int or not 0<=before<1<<256:raise ValueError('invalid fee accounting state')
  after=before+increment
  if after>=1<<256:raise ValueError('fee accounting overflow')
  writes[slot]=after
 return dict(**fee,writes=writes)
