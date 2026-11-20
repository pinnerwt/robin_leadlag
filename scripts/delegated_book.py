"""Pinned single-route adapter for Book; no I/O on the proposal path."""
from delegated_single_local import preview
PROFILE='delegated-single-v3-v1'
IMPLEMENTATION='0x0d160b31ade2dc16f8e22b2d965eb28531f4fc74'
CODE_HASH='0x6d1089a2056bc0aa4059904aee76b956a4d93295ca1b62120332eaf8d8f76a4f'
IMPLEMENTATION_HASH='0xa0796a336ee306fadfda78603ebb998f4a62d41236b340c1694dc7e183a0b1ea'

def pinned(profile):
 return (profile.get('profile')==PROFILE and profile.get('code_hash')==CODE_HASH and
  any(d.get('address')==IMPLEMENTATION and d.get('code_hash')==IMPLEMENTATION_HASH for d in profile.get('dependencies',[])))

def proposal(book,tx,profile):
 try:
  if not book.assume_success:raise ValueError('delegated routes require success assumption')
  if not pinned(profile):raise ValueError('unverified delegated code pins')
  if book.delegated_pins_stale:raise ValueError('delegation may have changed; checkpoint refresh required')
  if not tx.get('raw_transaction'):raise ValueError('missing transaction envelope for delegation guard')
  # Preview takes only recorded curves: missing upstream dependency state rejects.
  available={a:s for a,s in book.states.items() if a not in book.invalid}
  r=preview(tx['data'],available,book.meta,book.meta)
 except (ValueError,KeyError) as error:
  book.unsupported[tx['tx']]=str(error);return []
 touched={f['pool'] for f in r['fills']}
 book.states.update({a:r['curves'][a] for a in touched})
 book.expected[tx['tx']]=[(f['pool'],dict(kind='swap',**{k:v for k,v in f.items() if k not in ('pool','recorded')})) for f in r['fills']]
 book.partial[tx['tx']]=['Delegated V3 route assumes transaction success and full token credit; conditions unevaluated',
  'Skipped unrecorded suffix state: '+','.join(r['stale_dependencies'])]
 book.counts['decoded_transactions']+=1
 return sorted(touched)
