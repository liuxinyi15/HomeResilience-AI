"""Published adjusted outcomes, with explicit scenario transfer and no consumption-model input."""
import json
from pathlib import Path
from functools import lru_cache
ROOT=Path(__file__).resolve().parents[2]

@lru_cache(maxsize=1)
def evidence():return json.loads((ROOT/'data/processed/decision-evidence.json').read_text())

NAMES={'loft':'loft','cavity':'cavity','wall':'solid'}

def group_for(p):
 if p.property_type=='terraced':
  return {'mid':'Mid terrace','end':'End terrace'}.get(p.terrace_position,'All domestic properties')
 return {'semi-detached':'Semi detached','detached':'Detached'}.get(p.property_type,'All domestic properties')

def effect_for(measures,p):
 ids={m['id'] for m in measures};data=evidence()
 if p.heating!='gas' or p.property_type=='flat':return None,'Published gas-insulation impacts do not cover this heating/property profile.'
 if p.need_age=='4':return None,'Published insulation intervention cohorts exclude properties built from 2000 onwards.'
 if 'loft'in ids and ('wall'in ids or 'cavity'in ids):
  name=('Solid Wall' if 'wall'in ids else 'Cavity Wall')+' Insulation and Loft Insulation'
  return dict(data['combined'][name],name=name,selection='Published combination cohort; no property-type breakdown available. Replaces, rather than sums, single effects.'),None
 keys=[NAMES[x] for x in ['wall','cavity','loft'] if x in ids]
 if not keys:return None,'No matching published gas-impact evidence for this portfolio; unquantified is not zero benefit in reality.'
 key=keys[0];group=group_for(p);entry=data['groups'][key]['property_type'].get(group)
 # Do not silently impute suppressed subgroup cells with population estimates.
 if not entry or not entry['available']:return None,'The published '+group+' effect is suppressed or unavailable; no invented subgroup estimate is used.'
 label={'loft':'Loft Insulation','solid':'Solid Wall Insulation','cavity':'Cavity Wall Insulation'}[key]
 return dict(entry,name=label,selection='Published property-type marginal group: '+group+('. Terrace position is unknown, so the broad non-flat cohort is shown.' if p.property_type=='terraced' and p.terrace_position=='unknown' else '.')),None

def savings(measures,p,scenario='central'):
 effect,reason=effect_for(measures,p)
 unquantified=[m['name'] for m in measures if m.get('category')=='Energy' and m['id'] not in NAMES]
 from .applicability import assess
 applicability=assess(measures,p)
 if effect is None or not applicability['quantifiable']:return dict(available=False,central_kwh=None,objective_kwh=None,reason=applicability.get('reason') or reason,unquantified=unquantified,evidence_ids=applicability['evidence_ids'],applicability=applicability,unknown_effect='Excluded from the quantified gas preference; not assumed zero in reality.')
 annual=getattr(p,'annual_gas_kwh',None)
 baseline=annual if annual is not None else 10000
 fraction=effect[{'low':'p25_fraction','central':'median_fraction','high':'p75_fraction'}[scenario]]
 factor=evidence()['carbon']['kg_co2e_per_kwh']
 values={name:baseline*effect[key] for name,key in [('central','median_fraction'),('lower','p25_fraction'),('upper','p75_fraction')]}
 return dict(available=True,applicability=applicability,central_kwh=round(values['central'],1),objective_kwh=round(baseline*fraction,1),lower_kwh=round(values['lower'],1),upper_kwh=round(values['upper'],1),
  effect_name=effect['name'],median_fraction=effect['median_fraction'],p25_fraction=effect['p25_fraction'],p75_fraction=effect['p75_fraction'],n=effect['n'],group=effect['group'],selection=effect['selection'],
  published_group_median_kwh=effect['median_kwh'],baseline_kwh=baseline,baseline_origin='User-entered annual gas scenario; not independently verified or weather-normalised' if annual is not None else 'Standard reference: 10,000 kWh/year, not a predicted household bill',is_reference=annual is None,
  carbon=dict(central_kg_co2e=round(values['central']*factor,1),lower_kg_co2e=round(values['lower']*factor,1),upper_kg_co2e=round(values['upper']*factor,1),factor_kg_per_kwh=factor,basis='2026 gross-CV direct gas combustion only; excludes embodied and upstream emissions',evidence_id='ghg-gas-2026'),
  source_url=evidence()['registry'][effect['evidence_id']]['source_url'],evidence_ids=[effect['evidence_id'],'ghg-gas-2026','planning-utility'],unquantified=unquantified,
  interpretation='Scenario baseline × published matched-control group median fraction. No consumption-model prediction is used. This is not a validated individual treatment effect.',
  uncertainty='Published household adjusted-estimate quartiles transferred to a scenario baseline; not confidence bounds, not an individual prediction interval. Negative values are retained. No validated personal interval coverage is claimed.',
  limitations='Source cohorts exclude flats, post-1999 insulation properties, smart-meter transition periods and invalid/extreme readings. Government-scheme selection, private retrofit gaps, occupancy and rebound limit transfer. Groups are marginal; age/EPC/region cannot be crossed. Combined cohorts differ from single cohorts.')

def normalised_energy(measures,p,scenario='central'):
 s=savings(measures,p,scenario)
 return max(-100,min(100,s['objective_kwh']/2000*100)) if s['available'] else 0
