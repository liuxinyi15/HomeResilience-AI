"""Offline inference from a validated model's exact finite categorical prediction table."""
import json
import math
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

@lru_cache(maxsize=1)
def artifact():return json.loads((ROOT/'models/gas2024-lookup.json').read_text())
@lru_cache(maxsize=1)
def detail_artifact():return json.loads((ROOT/'models/gas2024-detail-lookup.json').read_text())
@lru_cache(maxsize=1)
def history_artifact():return json.loads((ROOT/'models/gas-history.json').read_text())
@lru_cache(maxsize=1)
def effects():return json.loads((ROOT/'data/processed/need-effects.json').read_text())

def area_band(area):return str(1 if area<=50 else 2 if area<=100 else 3 if area<=150 else 4 if area<=200 else 5)

@lru_cache(maxsize=256)
def predict(p):
 if p.heating!='gas':return dict(available=False,reason='The integrated NEED model targets gas-consuming homes. It is not applicable to oil, electric or heat-pump profiles.')
 try:a=artifact()
 except OSError:return dict(available=False,reason='Validated energy artifact unavailable. No empirical prediction is substituted.')
 lookup_type=p.property_type
 subtype_used=False
 if p.property_type=='terraced' and getattr(p,'terrace_position','unknown') in ['mid','end']:
  try:
   a=detail_artifact();lookup_type=p.terrace_position+'-terrace';subtype_used=True
  except OSError:pass
 ages=[p.need_age] if p.need_age!='unknown' else {'pre-1919':['1'],'1919-1980':['1','2','3'],'post-1980':['3','4']}[p.age]
 rows=[(age,a['lookup'].get('|'.join([lookup_type,area_band(p.area),age,'E12000003']))) for age in ages]
 rows=[(age,r) for age,r in rows if r and r['support_train']>=10]
 if not rows:return dict(available=False,reason='Insufficient training support for this property type, floor-area band and compatible age bands in Yorkshire.')
 total=sum(r['support_train'] for _,r in rows)
 value=sum(r['prediction_kwh']*r['support_train'] for _,r in rows)/total
 radius=a['interval']['radius_kwh'];low=max(1000,min(r['prediction_kwh'] for _,r in rows)-radius);high=min(50000,max(r['prediction_kwh'] for _,r in rows)+radius)
 group_metrics=a.get('subgroup_metrics',{}).get('FLOOR_AREA_BAND',{}).get(area_band(p.area),{})
 return dict(available=True,prediction_kwh=round(value),lower_kwh=round(low),upper_kwh=round(high),model=a['model'],reference_year=2024,test=a['test'],support_train=total,age_bands=[age for age,_ in rows],feature_values=dict(property_type=lookup_type,area_band=area_band(p.area),age_band=p.need_age,region='E12000003'),
  subtype_used=subtype_used,test_scope=a.get('test_scope','Original property holdout'),subgroup_interval_coverage=group_metrics.get('interval_coverage'),
  calibration_warning='The 90% target is marginal. Held-out coverage for this floor-area band was '+str(round(100*group_metrics.get('interval_coverage',0),1))+'%; a precise individual interval is not supported.' if group_metrics and group_metrics['interval_coverage']<.85 else None,
  age_handling='Exact NEED-compatible band' if p.need_age!='unknown' or len(ages)==1 else 'Training-support-weighted average over compatible age bands; interval is their envelope. Sparse bands omitted and disclosed.',
  interval_label='90% target marginal split-conformal interval; compatible-age envelope where age is uncertain',
  interval_test_coverage=a['interval']['test_coverage'],
  source_url='https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-anonymised-data-2026',
  evidence='Empirical prediction from valid 2024 NEED metered gas estimates',
  limitation='Retrospective population estimate, not a current bill, EPC, causal effect or guaranteed personal consumption. Consumption is weather-corrected and rounded in the source; current property metadata and household behaviour limit transfer.')

def history_values(readings):
 """Numeric features matching the fitted historical pipeline; optional older readings stay missing."""
 values=[readings.get(str(y)) for y in [2023,2022,2021]]
 present=[x for x in values if x is not None]
 mean=sum(present)/len(present)
 deviation=math.sqrt(sum((x-mean)**2 for x in present)/(len(present)-1)) if len(present)>1 else 0
 return values+[mean,values[0]-values[1] if values[1] is not None else None,values[0]/values[1] if values[1] is not None else None,deviation]

def predict_history(payload,p=None):
 if not isinstance(payload,dict) or set(payload)-{'source_year','weather_corrected','compatible_period','readings'}:raise ValueError('Invalid historical-input fields')
 if type(payload.get('source_year')) is not int or payload['source_year']!=2023:raise ValueError('This validated historical scenario requires source year 2023, predicting NEED year 2024')
 if payload.get('weather_corrected') is not True or payload.get('compatible_period') is not True:raise ValueError('Matching weather-corrected, valid metered NEED-year readings must be confirmed; ordinary calendar bills are not validated inputs')
 readings=payload.get('readings')
 if not isinstance(readings,dict) or set(readings)-{'2023','2022','2021'}:raise ValueError('Only gas readings for 2023, 2022 and 2021 are accepted; future/concurrent readings are excluded')
 if readings.get('2023') is None:raise ValueError('The 2023 gas reading is required')
 for year,value in readings.items():
  if value is not None and (type(value) not in [int,float] or not math.isfinite(value) or not 1000<=value<=50000):raise ValueError('Historical gas readings must be valid finite values from 1,000 to 50,000 kWh')
 try:a=history_artifact()
 except OSError:return dict(available=False,reason='Validated historical artifact unavailable')
 features=history_values(readings);prediction=0
 for weight,component in zip(a['weights'],a['components']):
  if component['kind']=='persistence':value=features[0]
  else:
   imputed=[component['imputer'][i] if v is None else v for i,v in enumerate(features)]
   imputed += [1.0 if features[i] is None else 0.0 for i in component['indicator_features']]
   value=component['intercept']+sum(coef*(v-mean)/scale for coef,v,mean,scale in zip(component['coef'],imputed,component['mean'],component['scale']))
  prediction+=weight*value
 if not math.isfinite(prediction):raise ValueError('Non-finite historical prediction')
 prediction=max(1000,min(50000,prediction));radius=a['interval']['radius_kwh']
 return dict(available=True,prediction_kwh=round(prediction),prediction_unrounded_kwh=prediction,lower_kwh=round(max(1000,prediction-radius)),upper_kwh=round(min(50000,prediction+radius)),reference_year=2024,model=a['model'],test=a['test'],persistence_test=a['persistence_test'],interval_test_coverage=a['interval']['test_coverage'],provided_years=[k for k,v in readings.items() if v is not None],scope='Separate historical-input scenario; portfolio impacts use published group effects independently of consumption predictions.',reference_period=a['reference_period'],limitation=a['limitation'])

def package_effect(measures,p):
 names={m['id'] for m in measures};name=None
 if p.heating!='gas' or p.property_type=='flat':return None
 if 'loft' in names and 'wall' in names:name='Solid Wall Insulation and Loft Insulation'
 elif 'loft' in names and 'cavity' in names:name='Cavity Wall Insulation and Loft Insulation'
 elif 'wall' in names:name='Solid Wall Insulation'
 elif 'cavity' in names:name='Cavity Wall Insulation'
 elif 'loft' in names:name='Loft Insulation'
 return effects()['effects'].get(name) if name else None

def savings(measures,p,scenario='central'):
 prediction=predict(p);effect=package_effect(measures,p)
 unquantified=[m['name'] for m in measures if m.get('category')=='Energy' and m['id'] not in ['loft','wall','cavity']]
 if not prediction['available'] or not effect:return dict(available=False,central_kwh=0,objective_kwh=0,reason='No applicable published gas-saving effect and compatible gas prediction for this package.',unquantified=unquantified)
 value=prediction['prediction_kwh'];fraction=effect[{'low':'p25_fraction','central':'median_fraction','high':'p75_fraction'}[scenario]]
 # Broad transfer range combines prediction envelope and observed household-effect dispersion.
 endpoints=[x*f for x in [prediction['lower_kwh'],prediction['upper_kwh']] for f in [effect['p25_fraction'],effect['p75_fraction']]]
 return dict(available=True,central_kwh=round(value*effect['median_fraction'],1),objective_kwh=round(value*fraction,1),lower_kwh=round(min(endpoints),1),upper_kwh=round(max(endpoints),1),effect_name=effect['name'],median_fraction=effect['median_fraction'],source_url=effect['source_url'],n=effect['n'],unquantified=unquantified,
  interpretation='Scenario transfer: predicted baseline gas × published NEED group median effect. Not an individually validated causal saving.',
  uncertainty='Range combines the prediction envelope with household effect quartiles; it is a stress range, not a confidence interval. Negative values mean possible consumption increases.')

def normalised_energy(measures,p,scenario='central'):
 s=savings(measures,p,scenario)
 return max(-100,min(100,100*s['objective_kwh']/2000))
