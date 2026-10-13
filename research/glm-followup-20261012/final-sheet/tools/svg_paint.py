"""Neutral parsing of computed SVG solid colors; eligibility belongs to each check.

None means the paint (for example a paint server) has not been measured. A known
transparent color has alpha zero, independently of its RGB components.
"""
import math
import re


def color_rgba(value):
    value=str(value or '').strip().lower()
    if value in ('none','transparent'):return (0.,0.,0.,0.)
    match=re.fullmatch(r'rgba?\(([^()]*)\)',value)
    if not match:return None
    parts=re.split(r'[,\s/]+',match.group(1).strip())
    if len(parts) not in (3,4):return None
    try:
        values=[float(v[:-1])*(255. if i<3 else 1.)/100 if v.endswith('%') else float(v)
                for i,v in enumerate(parts)]
        if not all(math.isfinite(v) for v in values):return None
        return tuple(max(0.,min(255.,v)) for v in values[:3])+(max(0.,min(1.,values[3])) if len(values)==4 else 1.,)
    except ValueError:return None

# Same neutral parser for Chrome's native geometry hit tests. Callers decide
# whether white ink, fill, width or opacity is eligible for their own rule.
COLOR_RGBA_JS = r'''
const colorRGBA = value => {
  value=String(value||'').trim().toLowerCase();
  if(['none','transparent'].includes(value)) return [0,0,0,0];
  const match=value.match(/^rgba?\(([^()]*)\)$/);
  if(!match) return null;
  const parts=match[1].trim().split(/[,\s/]+/);
  if(![3,4].includes(parts.length)) return null;
  const values=parts.map((v,i)=>v.endsWith('%')?Number(v.slice(0,-1))*(i<3?255:1)/100:Number(v));
  if(values.some(v=>!Number.isFinite(v))) return null;
  return [...values.slice(0,3).map(v=>Math.max(0,Math.min(255,v))),values.length===4?Math.max(0,Math.min(1,values[3])):1];
};
'''


def computed_length(value):
    """Resolved numeric/px computed lengths only; percentages need viewport evidence."""
    value=str(value or '').strip()
    if value.startswith('calc(') and value.endswith(')'):value=value[5:-1].strip()
    match=re.fullmatch(r'([-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?)(?:px)?',value)
    if not match:return None
    result=float(match[1])
    return result if math.isfinite(result) and result>=0 else None


def has_dash_gaps(value):
    value=str(value or 'none').strip()
    if value=='none':return False
    parts=[computed_length(v) for v in re.split(r'[ ,]+',value)]
    if not parts or any(v is None for v in parts):return None
    if len(parts)%2:parts*=2
    return any(v>0 for v in parts[1::2])
