"""Causal startup-only quote ratio approximation; validate against later swaps."""
import json,argparse
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--base',default='reports/metric-multi-latest');args=ap.parse_args()
B=Path(args.base);book=json.load(open('scripts/metric_spread_codebook.json'));manifest=json.load(open(B/'manifest.json'))
for m in manifest:
 s=json.load(open(m['seed']));p=s['pools'][0];w=bytes.fromhex(s['accounts']['0xe844701934d9c6085b292e428f41b911cc0b3872']['storage'][m['source_slot']][2:]);raw=int.from_bytes(w[:4]);price=(raw&((1<<27)-1))<<(raw>>27);unit=1<<64
 source=[price*unit*(1000000-book[w[4]])//10**14,-(-price*unit*(1000000+book[w[5]])//10**14),price*unit//10**8]
 out=p['quote_trace']['output'];actual=[int(out[2+i*64:66+i*64],16)for i in range(3)]
 p['source_calibration']=[[hex(a),hex(b)]for a,b in zip(actual,source)];p['source_calibration_assumption']='Fixed side-specific ratios from initial pinned provider quote only; not fitted to subsequent swaps. Guards remain omitted.'
 path=B/(m['symbol']+'-calibrated-seed.json');path.write_text(json.dumps(s));m['seed']=str(path)
(B/'calibrated-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
