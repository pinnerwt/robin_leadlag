"""Reproduce archived c9 callback argument capture with synthetic funding only."""
import json,subprocess
from pathlib import Path
from c9_router import C9
rows=[json.loads(l)['tx'] for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if (json.loads(l)['tx']['to'] or '').lower()==C9]
output=subprocess.check_output(['target/release/examples/router_prefix','reports/amm/routerc9-synthetic-seed.json'],input=''.join(json.dumps(r)+'\n' for r in rows),text=True)
Path('reports/amm/routerc9-callback-prefix.jsonl').write_text(output)
print(f'{len(rows)} prefix probes; not full execution/state parity')
