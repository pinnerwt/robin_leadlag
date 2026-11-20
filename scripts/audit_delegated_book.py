"""Independent checkpoint previews of pinned corpus routes, not chronological replay."""
import json
from pathlib import Path
from collections import Counter
from amm_feed_state import Book

def main():
 seed=json.loads(Path('captures/startup-v9-quotes.json').read_text())
 registry=json.loads(Path('reports/amm/delegated-single-registry.json').read_text());rows=[]
 for entry in map(json.loads,Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines()):
  tx=entry['tx']
  if (tx.get('to') or '').lower() not in registry['routers']:continue
  book=Book(seed,registry,True);touched=book.proposal(tx)
  rows.append(dict(tx=tx['tx'],touched=touched,reason=book.unsupported.get(tx['tx']),notes=book.partial.get(tx['tx']),
   status='checkpoint_preview_applied' if touched else 'unresolved',expected=book.expected.get(tx['tx'])))
 report=dict(anchor=seed['anchor']['hash'],counts=dict(Counter(r['status'] for r in rows)),transactions=rows,
  caveat='Each transaction independently starts from archived checkpoint. No chronological/historical parity or complete corpus claim. Logs not used.')
 Path('reports/amm/delegated-book-audit.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['counts']);print(dict(Counter(r['reason'] for r in rows if r['reason'])))
if __name__=='__main__':main()
