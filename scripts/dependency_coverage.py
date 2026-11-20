"""Deterministic pre-anchor trace-block selection and explicit coverage gaps."""
import json

def select_blocks(lines,tip,budget=64,window=1500):
 if budget<1 or window<1:raise ValueError('positive budget/window required')
 blocks={};all_routes=set();eligible=set();transactions=0
 for line in lines:
  r=json.loads(line)
  if r.get('kind')!='feed_tx' or r['sequence']>tip:continue
  route=((r.get('to') or '').lower(),r['from'].lower(),r.get('data','0x')[:10].lower())
  all_routes.add(route)
  if r['sequence']<=tip-window:continue
  blocks.setdefault(r['sequence'],set()).add(route);eligible.add(route);transactions+=1
 remaining=set(eligible);selected=[]
 while remaining and blocks and len(selected)<budget:
  block=max(blocks,key=lambda b:(len(blocks[b]&remaining),b))
  if not blocks[block]&remaining:break
  remaining-=blocks.pop(block);selected.append(block)
 return dict(selected_blocks=selected,tip=tip,window=window,budget=budget,eligible_transactions=transactions,
  observed_routes=len(all_routes),eligible_routes=len(eligible),covered_routes=len(eligible)-len(remaining),
  uncovered_eligible_routes=[list(r) for r in sorted(remaining)],
  outside_window_routes=[list(r) for r in sorted(all_routes-eligible)],
  observed_route_coverage_complete=not remaining and all_routes==eligible,
  execution_state_complete=False)
