"""Evidence-linked conditional flood design support; never a household damage model."""
import json,re
from pathlib import Path
from functools import lru_cache
ROOT=Path(__file__).resolve().parents[2]

@lru_cache(maxsize=1)
def evidence():return json.loads((ROOT/'data/processed/pfr-evidence.json').read_text())

def depth_context(p,hazard):
 if p.flood_depth_m is not None:return dict(lower_m=p.flood_depth_m,upper_m=p.flood_depth_m,origin='User-reported design depth above ground-floor level; not independently verified',status='reported')
 depth=hazard.get('depth_evidence',{})
 if depth.get('status')=='modelled_depth':
  bounds=[]
  for label in depth.get('depth_bands',[]):
   # Explicit metric labels only. Never turn unavailable or an unparsed band into zero.
   if 'm' not in label.lower():continue
   nums=[float(n) for n in re.findall(r'\d+(?:\.\d+)?',label)]
   if len(nums)==2:bounds.append((min(nums)/1000,max(nums)/1000) if 'mm' in label.lower() else (min(nums),max(nums)))
  if bounds:return dict(lower_m=min(b[0] for b in bounds),upper_m=max(b[1] for b in bounds),origin='Official area depth-band envelope, not threshold-relative surveyed property depth',status='area_band')
 return dict(lower_m=None,upper_m=None,origin='Design depth unavailable or not safely interpretable; survey required',status='unknown')

def screen(p,measure_id,hazard=None):
 record=evidence()['measures'].get(measure_id)
 if not record:return None
 depth=depth_context(p,hazard or {})
 reasons=[]
 if measure_id!='survey' and not p.ground_floor:reasons.append('No private occupied ground-floor works reported.')
 if measure_id in p.existing_protection:reasons.append('This protection is already reported; no duplicate installation benefit is assigned.')
 if measure_id in ['barrier','flood-door'] and set(p.existing_protection)&{'barrier','flood-door'}:reasons.append('An existing opening-protection system is reported; inspect/maintain it before considering replacement.')
 if measure_id=='barrier' and not p.can_deploy:reasons.append('Manual deployment cannot be relied on in this profile.')
 if measure_id=='air-bricks' and not p.air_bricks:reasons.append('No unprotected air-brick pathway reported.')
 if record['approach']=='resistance' and depth['upper_m'] is not None and depth['upper_m']>evidence()['policy']['resistance_depth_review_m']:
  reasons.append('Depth may exceed 0.6m: generic resistance prescription is deferred pending bespoke structural/product design; 0.6m is not a safe-depth guarantee.')
 if p.listed and measure_id in ['flood-door','flooring']:reasons.append('Listed fabric requires a conservation-led bespoke design outside automatic selection.')
 return dict(eligible=not reasons,status='deferred' if reasons else 'enabling_survey' if measure_id=='survey' else 'conditional_on_survey',reasons=reasons,depth=depth,record=record)

def pathways(p):
 # Vent presence is reported; the other mechanisms remain survey questions, not measured vulnerabilities.
 if not p.ground_floor:return set()
 return {'openings','drainage','services','floor_recovery'}|({'vents'} if p.air_bricks else set())

def coverage(measures,p,hazard,scenario='central'):
 data=evidence()['measures'];relevant=pathways(p)
 existing=set().union(*(set(data[i]['pathways']) for i in p.existing_protection if i in data)) if p.existing_protection else set()
 relevant-=existing;covered=set()
 for measure in measures:
  identifier=measure['id'];s=screen(p,identifier,hazard)
  if s and s['eligible']:covered.update(data[identifier]['pathways'])
 covered &= relevant
 score=100*len(covered)/len(relevant) if relevant else 0
 return dict(covered=sorted(covered),remaining_relevant=sorted(relevant),already_reported=sorted(existing),score=round(min(100,score*{'low':.8,'central':1,'high':1.2}[scenario]),3),
   evidence_id='pfr-pathway-preference',unit='Conditional pathway-coverage preference; not effectiveness, damage reduction or probability',quantitative_damage_reduction=None,
   uncertainty='Unconfirmed routes and equal pathway importance are planning assumptions; no empirical uncertainty interval is assigned.')

def recommendation(measure,p,hazard):
 result=screen(p,measure['id'],hazard)
 if not result:return None
 r=result['record'];result=dict(result)
 result.update(vulnerability=r['vulnerability'],supported_benefit=r['supported_benefit'],quantitative_damage_reduction=None,maintenance=r['maintenance'],failure_conditions=r['failure_conditions'],unknowns=r['unknowns'],evidence_class=r['evidence_class'],evidence_ids=r['evidence_ids'],cost_uncertainty=dict(low=measure['cost_low'],central=measure['cost_base'],high=measure['cost_high'],origin=measure['cost_origin']),
  source_references=[dict(id=i,url=evidence()['sources'][i]['source_url'],locator=evidence()['sources'][i]['locator']) for i in r['evidence_ids']])
 return result
