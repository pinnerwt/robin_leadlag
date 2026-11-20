import json,pathlib
R=pathlib.Path('reports/ohio-latest-20261119T2103Z');w=json.load(open(R/'window.json'));bad=[r for r in map(json.loads,open(R/'iex-invalid-boundaries.jsonl'))if w['start_ns']<=r['recv_ns']<=w['end_ns']];print('in-window invalid/gaps',len(bad))
for p in R.glob('*-iex-bbo.jsonl'):
 ticker=p.name.removesuffix('-iex-bbo.jsonl');markers=[dict(recv_ns=r['recv_ns'],mono_ns=r['recv_ns']-w['origin_ns'],invalid=True)for r in bad if r.get('symbol',ticker)==ticker];rows=list(map(json.loads,open(p)))
 if markers:rows+=markers;rows.sort(key=lambda r:r['recv_ns']);p.write_text(''.join(json.dumps(r)+'\n'for r in rows))
 print(ticker,len(rows),len(markers))
