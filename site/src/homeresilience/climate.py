"""Link official area hazards to survey-led resilience options without a damage model."""
from .flood import exposure

def climate_context(lon,lat,p):
 keys=['rofrs','present_defended_100','present_undefended_100','future_defended_100','future_undefended_100','depth_defended_100']
 scenarios={key:dict(exposure(lon,lat,key),evidence_id='ea-'+key) for key in keys}
 links=[]
 if p.ground_floor:
  links.extend([
   dict(measure_id='survey',hazard='Uncertain water-entry paths and design depth',reason='Assess threshold levels, routes, groundwater, duration and safe resistance before specifying physical works.'),
   dict(measure_id='flood-door' if not p.can_deploy else 'barrier',hazard='Potential water entry at external openings',reason='Discuss passive doors or deployable guards only after a survey establishes suitable depth, structure, maintenance and safe operation.'),
   dict(measure_id='valve',hazard='Potential drainage backflow',reason='Drainage assessment must establish backflow routes and safe valve suitability; the EA extent alone does not identify this route.'),
   dict(measure_id='electrics',hazard='Potential interruption if services are inundated',reason='Survey-led adaptation may reduce recovery burden; property-specific avoided damage is unquantified.')])
  if p.air_bricks:links.append(dict(measure_id='air-bricks',hazard='Reported ground-floor vents',reason='Inspect suitable self-closing vents while preserving required ventilation; actual effectiveness is unquantified.'))
 return dict(scenarios=scenarios,links=links,geographic_scope='York bbox [-1.12, 53.93, -1.04, 53.99], England; no UK&I-wide coverage claimed',
  interpretation='Official modelled flood exposure and scenario extents, not a property-damage probability, loss estimate or insurance decision.',
  gaps=['Surface water and groundwater not integrated.','Published depth may be explicitly unavailable; do not substitute zero.','Future RCP8.5 extent is a scenario for river Central 2080s / sea Upper End 2125, not a forecast to 2036.','Outside one modelled extent does not establish low risk; local surveys and all official flood sources remain necessary.'],
  future_change='Within future extent, outside comparable present defended extent' if scenarios['future_defended_100']['status']=='within_modelled_extent' and scenarios['present_defended_100']['status']=='outside_modelled_extent' else 'Inspect present/future extent membership separately; no numerical probability change is inferred.')
