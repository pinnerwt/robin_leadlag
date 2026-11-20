"""Offline bounded storage adapter; missing tick words remain unavailable."""
from bootstrap_state import mapping
from v3_state import State

def load(storage,fee,spacing):
 s={int(k,16):int(v,16) for k,v in storage.items()}
 if 0 not in s or 4 not in s:raise ValueError('missing V3 core')
 word=s[0];tick=(word>>160)&((1<<24)-1);tick=tick-(1<<24) if tick&(1<<23) else tick
 center=(tick//spacing)>>8;bitmap={};ticks={}
 for index in range(center-1,center+2):
  key=int(mapping(index,6),16)
  if key not in s:continue
  bitmap[index]=s[key]
  for bit in range(256):
   if not s[key]&(1<<bit):continue
   t=(index*256+bit)*spacing;slot=int(mapping(t,5),16)
   if slot in s:
    packed=s[slot];net=packed>>128;net=net-(1<<128) if net&(1<<127) else net
    ticks[t]=(packed&((1<<128)-1),net)
 return State(word&((1<<160)-1),tick,s[4],fee,spacing,bitmap,ticks)
