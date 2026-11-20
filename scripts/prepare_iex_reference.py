"""Prepare causal IEX BBO with explicit invalid/disconnect boundaries."""
import argparse,json,math
from pathlib import Path
from iex_pool_hy import load_iex
from tape import records

def main():
 p=argparse.ArgumentParser();p.add_argument('tape',type=Path);p.add_argument('directory',type=Path);a=p.parse_args();w=json.load(open(a.directory/'window.json'));origin=w['origin_ns']
 series,bbos,quality=load_iex(records([a.tape]));(a.directory/'iex-quality.json').write_text(json.dumps(quality,indent=2))
 for ticker,rows in bbos.items():
  rows=[dict(r,mono_ns=r['recv_ns']-origin) for r in rows if w['start_ns']<=r['recv_ns']<=w['end_ns']]
  rows += [dict(recv_ns=t,mono_ns=t-origin,invalid=True) for t,b,a in series[ticker] if not math.isfinite(b) and w['start_ns']<=t<=w['end_ns']]
  rows.sort(key=lambda r:r['recv_ns'])
  (a.directory/(ticker+'-iex-bbo.jsonl')).write_text(''.join(json.dumps(r)+'\n'for r in rows));print(ticker,len(rows),sum(bool(r.get('invalid'))for r in rows),flush=True)
if __name__=='__main__':main()
