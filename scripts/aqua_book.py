"""Opt-in shared Aqua state for the optimistic follower; no runtime requests."""
from amm_feed_state import Book
from c7_state_bridge import Bridge
C9='0xc9a1dcff54632b408f2b0e048d8b7d3261697144'
R777='0x7777857616fb37f0cfa262e9bb945e828312df17'

class AquaBook(Book):
 def __init__(self,seed,registry,assume_success=True):
  super().__init__(seed,registry,assume_success)
  if not assume_success:raise ValueError('Aqua state requires explicit success assumption')
  if not registry:raise ValueError('Aqua state requires pinned router registry')
  for address in (C9,R777):
   profile=registry.get('routers',{}).get(address,{})
   if not profile.get('code_hash'):raise ValueError('missing Aqua router code pin')
  if not registry['routers'][C9].get('implementation_code_hash'):raise ValueError('missing C9 implementation pin')
  dependencies={d['address'].lower() for profile in registry['routers'].values() for d in profile.get('dependencies',[]) if d.get('code_hash')}
  if not {'0x111111338c5091e8440b67b168bae16a668ac0de','0x1111113ccf1426a8e30e2bff5e005d929bf6a90a'}<=dependencies:
   raise ValueError('missing Aqua execution dependency pins')
  self.aqua=Bridge(seed,seed['aqua'])
  # One shared dictionary: ordinary V3 swaps/liquidity changes remain visible.
  self.aqua.states=self.states
 def proposal(self,tx):
  self.observe_envelope(tx)
  target=(tx.get('to') or '').lower();data=tx.get('data','')
  handled=(target==C9 and data.startswith('0xc7e280dd')) or (target==R777 and data.startswith('0x3fa72595'))
  if handled:
   if self.invalid:
    self.aqua.invalidate('V3 state invalid before dependent route')
   try:result=self.aqua.apply_transaction(target,data)
   except (ValueError,KeyError) as error:
    self.aqua.invalidate('dependent route unresolved: '+str(error))
    self.unsupported[tx['tx']]=str(error)
    self.counts['simulation_rejected']+=1
    return []
   pool=result['pool']
   self.expected[tx['tx']]=[(pool,dict(kind='swap',**result['v3']))]
   self.partial[tx['tx']]=['Aqua/V3 local state applied under success assumption; full transaction execution unverified']
   self.counts['decoded_transactions']+=1
   return [pool]
  touched=super().proposal(tx)
  if tx['tx'] in self.unsupported or tx['tx'] in self.partial:
   # An unknown/nested transaction may change allocations or token inventories.
   # Keep ordinary V3 behavior, but never reuse the stale Aqua book afterward.
   self.aqua.invalidate('unresolved transaction since Aqua checkpoint: '+tx['tx'])
  return touched

def make_book(seed,registry=None,assume_success=False):
 if 'aqua' in seed:return AquaBook(seed,registry,assume_success)
 return Book(seed,registry,assume_success)
