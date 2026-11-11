"""Complete official feature-query lookups; no absence-to-low-risk inference."""
import json,math
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

@lru_cache(maxsize=1)
def manifest():return json.loads((ROOT/'data/processed/flood/manifest.json').read_text())

@lru_cache(maxsize=7)
def index(layer):
 m=manifest()['layers'][layer]
 doc=json.loads((ROOT/m['path']).read_text())
 try:
  from shapely.geometry import shape
  from shapely.strtree import STRtree
  geometries=[shape(f['geometry']) for f in doc['features']]
  return STRtree(geometries),geometries,[dict(id=f['id'],properties=f['properties']) for f in doc['features']],None
 except ImportError:
  def vertices(g):
   coords=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
   return [p for poly in coords for ring in poly for p in ring]
  boxes=[]
  for f in doc['features']:
   v=vertices(f['geometry']);boxes.append((min(p[0] for p in v),min(p[1] for p in v),max(p[0] for p in v),max(p[1] for p in v)))
  return None,None,doc['features'],boxes

def matches(layer,lon,lat):
 tree,geometries,records,boxes=index(layer)
 if tree is not None:
  from shapely.geometry import Point
  point=Point(lon,lat)
  return [records[int(i)] for i in tree.query(point) if geometries[int(i)].covers(point)]
 from .engine import contains
 return [r for r,b in zip(records,boxes) if b[0]<=lon<=b[2] and b[1]<=lat<=b[3] and contains(r['geometry'],lon,lat)]

def exposure(lon,lat,layer='rofrs'):
 if type(lon) not in [float,int] or type(lat) not in [float,int] or not math.isfinite(lon+lat) or not(-180<=lon<=180 and -90<=lat<=90):raise ValueError('Coordinates must be finite longitude/latitude values')
 m=manifest()
 base=dict(category='Unknown',feature_id=None,lon=lon,lat=lat,kind='Official modelled area data',coverage='complete_query',layer=layer,limitation='Area evidence only, not a property loss probability. No mapped band does not establish safety.')
 if layer not in m['layers']:return dict(base,status='source_unavailable',kind='Requested source unavailable',coverage='unavailable')
 west,south,east,north=m['bbox']
 if not(west<=lon<=east and south<=lat<=north):return dict(base,status='outside_coverage',kind='Outside pilot coverage',coverage='outside')
 found=matches(layer,lon,lat)
 if layer=='rofrs':
  from .engine import classify
  order={'High':4,'Medium':3,'Low':2,'Very Low':1,'Unknown':0}
  f=max(found,key=lambda f:order[classify(f['properties'])],default=None)
  return dict(base,category=classify(f['properties']) if f else 'Unknown',feature_id=f['id'] if f else None,status='mapped_band' if f else 'covered_no_mapped_band',kind='Official modelled area data' if f else 'Covered query, no published band')
 if layer.startswith('depth'):
  missing=[f for f in found if str(f['properties'].get('depth_band','')).lower()=='unavailable']
  known=[f for f in found if f not in missing]
  status='source_unavailable' if missing else 'modelled_depth' if known else 'covered_no_mapped_depth'
  return dict(base,status=status,depth_bands=sorted({f['properties']['depth_band'] for f in known}),feature_id=found[0]['id'] if found else None,
   unavailable_geometry_matched=bool(missing),kind='Depth unavailable in publisher data' if missing else 'Official modelled depth scenario',coverage='source_unavailable' if missing else 'complete_query',
   limitation='Scenario flood depth is modelled, not observed damage. Explicit unavailable polygons override depth claims; no match does not prove zero depth.')
 return dict(base,status='within_modelled_extent' if found else 'outside_modelled_extent',feature_id=found[0]['id'] if found else None,
  modelled_flood_sources=sorted({f['properties'].get('flood_source','undefined') for f in found}),
  kind='Official modelled scenario extent',aep='0.1% rivers/sea' if layer.endswith('_1000') else '1% rivers / 0.5% sea',
  climate='UKCP18 RCP8.5: rivers Central 2080s (2070–2125); sea Upper End to 2125; current defence assumptions retained' if layer.startswith('future') else 'Present day',
  limitation='Being outside one scenario extent is not a low-risk classification. Defended scenarios assume intended defence operation, not failure. Area scenario only, not a property prediction.')
