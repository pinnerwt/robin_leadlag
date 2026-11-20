"""Derive per-pool source binding from pinned source-contract storage, offline."""
import json,argparse
from pathlib import Path
from bootstrap_state import mapping
ap=argparse.ArgumentParser();ap.add_argument('--capture',default='captures/metric-hybrid-20261115T235506Z');ap.add_argument('--output',default='reports/metric-multi-latest');args=ap.parse_args()
BASE=Path(args.output);BASE.mkdir(parents=True,exist_ok=True)
s=json.load(open(Path(args.capture)/'checkpoint.json'))
manifest=[]
for p in s['pools']:
 key=int(mapping(int(p['pool'],16),3),16)+1
 feed=s['accounts'][p['source'].lower()]['storage']['0x'+format(key,'064x')]
 assert feed.startswith('0x8dfdc825') and feed.endswith('00')
 ident=(int(feed,16)>>8)&255
 slot=feed[:42]+format(ident,'024x')
 assert slot in s['accounts']['0xe844701934d9c6085b292e428f41b911cc0b3872']['storage']
 p=dict(p,source_slot=slot,feed_topic=feed,word_id=ident)
 assert p['decimals']==[18,6]
 stem=p['binance_symbol'];seed=dict(s,pools=[p]);path=BASE/(stem+'-seed.json');path.write_text(json.dumps(seed))
 manifest.append(dict(symbol=stem,pool=p['pool'].lower(),feed_topic=feed,word_id=ident,source_slot=slot,seed=str(path)))
(BASE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
