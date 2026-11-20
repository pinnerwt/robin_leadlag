"""Observed current-code fixed band; returns branch only, not a swap amount."""
LOWER=0xfff67f55a235ee97af0549fc
UPPER=0x100098104adc9acdec9701b9f

def branch(sqrt_v3,sqrt_v4):
 if any(type(x) is not int or not 0<x<1<<160 for x in (sqrt_v3,sqrt_v4)):raise ValueError('invalid sqrt price')
 ratio=(sqrt_v3*((1<<192)//sqrt_v4))>>96
 return dict(ratio=ratio,branch=1 if ratio>UPPER else 2 if ratio<LOWER else 0,execution_complete=False)
