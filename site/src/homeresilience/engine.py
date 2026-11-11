import json
import math
import copy
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class Property:
    property_type: str = 'terraced'
    age: str = 'pre-1919'
    area: int = 90
    epc: str = 'D'
    ground_floor: bool = True
    loft_uninsulated: bool = True
    air_bricks: bool = True
    listed: bool = False
    can_deploy: bool = True
    heating: str = 'gas'
    need_age: str = 'unknown'
    wall_type: str = 'unknown'
    terrace_position: str = 'unknown'
    annual_gas_kwh: int = None
    flood_depth_m: float = None
    existing_protection: tuple = ()
    completed_measures: tuple = ()

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict) or set(data) - set(cls.__dataclass_fields__):
            raise ValueError('Unknown property fields')
        data=dict(data)
        protection=data.get('existing_protection',())
        allowed={'barrier','flood-door','air-bricks','valve','electrics','flooring'}
        if not isinstance(protection,(list,tuple)) or any(type(x) is not str or x not in allowed for x in protection):
            raise ValueError('Unknown existing protection; use the listed measure IDs')
        data['existing_protection']=tuple(sorted(set(protection)))
        completed=data.get('completed_measures', ())
        allowed_completed={m['id'] for m in catalogue()}
        if not isinstance(completed,(list,tuple)) or any(type(i) is not str or i not in allowed_completed for i in completed):
            raise ValueError('Unknown completed measure')
        data['completed_measures']=tuple(sorted(set(completed)))
        data['existing_protection']=tuple(sorted(set(protection) | (set(completed) & allowed)))
        p = cls(**data)
        choices = {'property_type': ['terraced','semi-detached','detached','flat'],
                   'age': ['pre-1919','1919-1980','post-1980'], 'epc': list('ABCDEFG')+['unknown'],
                   'heating': ['gas','oil','electric','heat-pump'],
                   'need_age':['unknown','1','2','3','4'], 'wall_type':['unknown','solid','cavity','insulated'],
                   'terrace_position':['unknown','mid','end']}
        for key, options in choices.items():
            if getattr(p,key) not in options:
                raise ValueError('Invalid ' + key)
        if type(p.area) is not int or not 20 <= p.area <= 500:
            raise ValueError('Floor area must be a whole number from 20 to 500 m²')
        for key in ['ground_floor','loft_uninsulated','air_bricks','listed','can_deploy']:
            if type(getattr(p,key)) is not bool:
                raise ValueError(key + ' must be true or false')
        if p.need_age!='unknown' and p.need_age not in {'pre-1919':['1'],'1919-1980':['1','2','3'],'post-1980':['3','4']}[p.age]:
            raise ValueError('The NEED construction band conflicts with the construction period')
        if p.terrace_position!='unknown' and p.property_type!='terraced':raise ValueError('Terrace position applies only to a terraced property')
        if p.annual_gas_kwh is not None and (type(p.annual_gas_kwh) is not int or not 2500<=p.annual_gas_kwh<=50000):
            raise ValueError('Optional annual gas scenario must be a whole number from 2,500 to 50,000 kWh')
        if p.flood_depth_m is not None and (type(p.flood_depth_m) not in [int,float] or not math.isfinite(p.flood_depth_m) or not 0<=p.flood_depth_m<=5):
            raise ValueError('Optional design flood depth must be finite, from 0 to 5 metres')
        return replace(p, loft_uninsulated=False if 'loft' in completed else p.loft_uninsulated,
                       wall_type='insulated' if {'wall','cavity'}.intersection(completed) else p.wall_type)

@lru_cache(maxsize=1)
def catalogue():
    return json.loads((ROOT / 'data/processed/interventions-v2.json').read_text())

@lru_cache(maxsize=1)
def geography():
    return json.loads((ROOT / 'data/processed/flood/rofrs.geojson').read_text())

def in_ring(x, y, ring):
    inside = False
    for a,b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > y) != (b[1] > y):
            if x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
                inside = not inside
    return inside

def contains(geometry, x, y):
    polygons = geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
    return any(in_ring(x,y,rings[0]) and not any(in_ring(x,y,h) for h in rings[1:]) for rings in polygons)

def classify(properties):
    # Only the publisher's explicit band field may establish a classification.
    v = str(properties.get('risk_band','')).strip().lower()
    if v in ['high','medium','low','very low']:
        return v.title()
    return 'Unknown'

def exposure(lon, lat, layer='rofrs'):
    from .flood import exposure as query
    return query(lon,lat,layer)

def assess(p, hazard):
    factors = []
    if p.ground_floor: factors.append(dict(label='Ground-floor exposure', explanation='Water can enter occupied ground-floor space.', points=30))
    if p.air_bricks and p.ground_floor: factors.append(dict(label='Air-brick entry paths', explanation='Unprotected vents may admit floodwater; ventilation must be preserved.',points=15))
    if p.age=='pre-1919': factors.append(dict(label='Traditional construction',explanation='Moisture behaviour needs a specialist assessment; age alone does not prove flood vulnerability.',points=10))
    if not p.can_deploy: factors.append(dict(label='Passive protection preferred',explanation='Temporary barriers are excluded because deployment is impractical.',points=15))
    energy = {'A':5,'B':15,'C':30,'D':50,'E':65,'F':80,'G':90,'unknown':None}[p.epc]
    return dict(exposure=hazard, vulnerability_index=min(100,sum(f['points'] for f in factors)),
                factors=factors, energy_priority=energy,
                label='Heuristic planning indicators, not calibrated risk, EPC or loss predictions',
                input_origin='User-provided or explicitly synthetic demo profile; no EPC retrieval',
                uncertainty=['No observed property damage labels or site survey; scenario depth may be explicitly unavailable.',
                             'Surface water and groundwater are not assessed. Future extents are separate area scenario evidence.',
                             'Unknown mapped exposure still warrants an official risk check.'])

def eligibility(p, measure, hazard=None):
    if measure['id'] in p.completed_measures:
        return 'Already recorded as complete. Review it in the Home Resilience Passport.'
    if measure['id'] in {'wall','cavity'} and {'wall','cavity'}.intersection(p.completed_measures):
        return 'Existing wall insulation is recorded. Review its condition before specifying further wall work.'
    if measure['id'] in ['survey','barrier','flood-door','air-bricks','valve','electrics','flooring']:
        from .pfr import screen
        result=screen(p,measure['id'],hazard)
        if not result['eligible']:return ' '.join(result['reasons'])
    key = measure['eligibility']
    if key=='ground' and not p.ground_floor: return 'No private ground-floor works in this profile.'
    if key=='barrier' and (not p.ground_floor or not p.can_deploy): return 'Needs ground-floor access and someone able to deploy it.'
    if key=='air' and (not p.ground_floor or not p.air_bricks): return 'No applicable ground-floor air bricks reported.'
    if key=='loft' and (p.property_type=='flat' or not p.loft_uninsulated): return 'No uninsulated private loft reported.'
    if key=='wall' and (p.property_type=='flat' or p.listed): return 'Shared or listed fabric requires a bespoke route outside this pilot.'
    if key=='heat' and (p.property_type=='flat' or p.heating=='heat-pump'): return 'Shared system or an existing heat pump; bespoke assessment required.'
    if key=='heat':return 'Heat-pump system design and consumption impact need specialist evidence. This prototype defers automatic selection rather than assigning an unsupported energy saving.'
    if key in ['solid','cavity']:
        if p.property_type=='flat' or p.listed:return 'Shared or listed fabric needs a bespoke professional route.'
        if p.wall_type!=key:return 'Confirm an uninsulated '+key+' wall before this measure can be considered.'
    return None

def benefits(measures, p, hazard, scale=1, benefit_scenario='central', mode='evidence'):
    # Diminishing returns are an explicit modelling assumption, not measured effectiveness.
    scores=[]
    for dimension in ['flood','energy','comfort']:
        if dimension=='flood' and mode=='evidence':
            from .pfr import coverage
            scores.append(round(coverage(measures,p,hazard,benefit_scenario)['score']*scale,3))
            continue
        if dimension=='energy' and mode=='evidence':
            from .impacts import normalised_energy
            scores.append(round(normalised_energy(measures,p,benefit_scenario)*scale,3) if hazard.get('coverage')!='outside' else 0)
            continue
        remaining=1.0
        for m in measures:
            b=m['benefit'][dimension]*scale
            if mode=='evidence':b *= {'low':.8,'central':1,'high':1.2}[benefit_scenario]
            if dimension=='flood':
                b *= {'High':1,'Medium':.85,'Low':.65,'Very Low':.45,'Unknown':.65}[hazard['category']]
                b *= 1 if p.ground_floor else .25
            if dimension=='energy':
                b *= {'A':.2,'B':.35,'C':.6,'D':.85,'E':1,'F':1.1,'G':1.15,'unknown':.7}[p.epc]
            remaining *= 1-min(.95,b/100)
        scores.append(round(100*(1-remaining),3))
    return scores

WEIGHTS={'balanced':(.45,.35,.2),'flood':(.75,.1,.15),'energy':(.1,.75,.15)}

def utility(values, weights): return round(sum(a*b for a,b in zip(values,weights)),4)

def valid_subset(selected, completed=()):
    ids={m['id'] for m in selected} | set(completed)
    return all(set(m['requires']) <= ids and not (set(m['excludes']) & ids) for m in selected)

def pareto_rows(rows):
    """Exact cost-minimising, three-benefit-maximising nondominance, no scalarisation."""
    frontier=[]
    for row in sorted(rows,key=lambda r:(r['cost'],*[-v for v in r['benefits']],tuple(r['ids']))):
        if any(other['cost']<=row['cost'] and all(a>=b for a,b in zip(other['benefits'],row['benefits']))
               and (other['cost']<row['cost'] or other['benefits']!=row['benefits']) for other in frontier):continue
        # Keep distinct equivalent portfolios: they can differ in high-cost robustness.
        frontier.append(row)
    return frontier

def solve(p, hazard, budget, priority='balanced', scenario='base', benefit_scenario='central', cost_overrides=None, mode='evidence', *, decision_intelligence=False):
    if type(budget) not in (int,float) or not math.isfinite(budget) or not 0 <= budget <= 100000:
        raise ValueError('Budget must be between £0 and £100,000')
    if priority not in WEIGHTS or scenario not in ['low','base','high']:
        raise ValueError('Unknown priority or cost scenario')
    if benefit_scenario not in ['low','central','high'] or mode not in ['evidence','legacy']:raise ValueError('Unknown benefit scenario or evidence mode')
    measures=copy.deepcopy(catalogue())
    overrides={} if cost_overrides is None else cost_overrides
    if not isinstance(overrides,dict) or set(overrides)-{m['id'] for m in measures}:raise ValueError('Unknown cost override measure')
    for m in measures:
        if m['id'] not in overrides:continue
        value=overrides[m['id']]
        if not isinstance(value,dict) or set(value)!={'low','base','high'}:raise ValueError('Each cost override requires low, base and high')
        for key in ['low','base','high']:
            x=value[key]
            if type(x) not in [int,float] or not math.isfinite(x) or not 0<=x<=100000:raise ValueError('Quote costs must be finite and between £0 and £100,000')
        if not value['low']<=value['base']<=value['high']:raise ValueError('Quote range must satisfy low ≤ base ≤ high')
        for key in ['low','base','high']:m['cost_'+key]=round(value[key],2)
        m['cost_origin']='User-entered quote range; not independently verified'
    eligible=[m for m in measures if eligibility(p,m,hazard) is None]
    excluded=[dict(id=m['id'],name=m['name'],reason=eligibility(p,m,hazard)) for m in measures if eligibility(p,m,hazard)]
    rows=[];all_rows=[]
    cost_key={'low':'cost_low','base':'cost_base','high':'cost_high'}[scenario]
    for mask in range(1 << len(eligible)):
        chosen=[m for i,m in enumerate(eligible) if mask & (1<<i)]
        cost=round(sum(m[cost_key] for m in chosen),2)
        if not valid_subset(chosen, p.completed_measures): continue
        values=benefits(chosen,p,hazard,benefit_scenario=benefit_scenario,mode=mode)
        row=dict(ids=[m['id'] for m in chosen],cost=cost,cost_base=round(sum(m['cost_base'] for m in chosen),2),
                         cost_low=round(sum(m['cost_low'] for m in chosen),2),cost_high=round(sum(m['cost_high'] for m in chosen),2),
                         benefits=values,utility=utility(values,WEIGHTS[priority]))
        all_rows.append(row)
        if cost<=budget:rows.append(row)
    nondominated=pareto_rows(rows)
    def best(weights):
        return max(nondominated,key=lambda r:(utility(r['benefits'],weights),-r['cost'],tuple(r['ids'])))
    names=[('Your priorities',WEIGHTS[priority]),('Flood first',WEIGHTS['flood']),('Energy first',WEIGHTS['energy'])]
    packages=[]
    for name,w in names:
        r=best(w)
        if any(x['ids']==r['ids'] for x in packages): continue
        packages.append(dict(r,name=name,objective_score=utility(r['benefits'],w)))
    # A distinct cheaper efficient alternative, including the no-spend option.
    frontier=[]; maximum=-1
    for r in sorted(rows,key=lambda r:(r['cost'],-r['utility'])):
        if r['utility'] > maximum:
            frontier.append(r);maximum=r['utility']
    if len(packages)<2:
        cheaper=[r for r in frontier if r['cost'] < packages[0]['cost']]
        if cheaper: packages.append(dict(cheaper[len(cheaper)//2],name='Smaller first step',objective_score=cheaper[len(cheaper)//2]['utility']))
    # Rerank every structurally feasible portfolio under all 3 × 3 assumptions.
    by_id={m['id']:m for m in eligible};case_utilities={};case_vectors={};stress=[]
    for row in all_rows:
        chosen=[by_id[i] for i in row['ids']]
        case_vectors[tuple(row['ids'])]={case:benefits(chosen,p,hazard,benefit_scenario=case,mode=mode) for case in ['low','central','high']}
        case_utilities[tuple(row['ids'])]={case:utility(v,WEIGHTS[priority]) for case,v in case_vectors[tuple(row['ids'])].items()}
    for cost_case in ['low','base','high']:
        for benefit_case in ['low','central','high']:
            pool=[row for row in all_rows if row['cost_'+cost_case]<=budget]
            winner=max(pool,key=lambda r:(case_utilities[tuple(r['ids'])][benefit_case],-r['cost_'+cost_case],tuple(r['ids'])))
            stress.append(dict(cost_case=cost_case,benefit_case=benefit_case,ids=winner['ids'],cost=winner['cost_'+cost_case],utility=case_utilities[tuple(winner['ids'])][benefit_case],feasible_count=len(pool)))
    def stability(row):
        key=tuple(row['ids']);cases=[]
        for case in stress:
            feasible=row['cost_'+case['cost_case']]<=budget
            score=case_utilities[key][case['benefit_case']]
            cases.append(dict(cost_case=case['cost_case'],benefit_case=case['benefit_case'],budget_feasible=feasible,regret=round(max(0,case['utility']-score),4) if feasible else None,selected_again=set(row['ids'])==set(case['ids'])))
        feasible_cases=[c for c in cases if c['budget_feasible']]
        return dict(feasible_cases=len(feasible_cases),total_cases=9,selected_again=sum(c['selected_again'] for c in cases),max_regret=max(c['regret'] for c in feasible_cases) if feasible_cases else None,cases=cases,interpretation='Enumerated assumption stress tests, not probabilities or confidence intervals. Regret is optimum minus fixed-package utility within each feasible scenario.')
    # A conservative alternative is efficient in current objectives and affordable at high allowances.
    robust_pool=[r for r in all_rows if r['cost_high']<=budget]
    if robust_pool:
        robust=min(robust_pool,key=lambda r:(stability(r)['max_regret'],-r['utility'],r['cost'],tuple(r['ids'])))
        if not any(x['ids']==robust['ids'] for x in packages):packages.append(dict(robust,name='Stable within tested assumptions',objective_score=robust['utility']))
    # Simple cost-prioritised feasible baseline, including dependency bundles.
    greedy=[]
    lookup={m['id']:m for m in eligible}
    for m in sorted(eligible,key=lambda m:(m[cost_key],m['id'])):
        bundle={x['id']:x for x in greedy}
        for required in m['requires']:
            if required in lookup: bundle[required]=lookup[required]
        bundle[m['id']]=m
        candidate=list(bundle.values())
        if valid_subset(candidate, p.completed_measures) and round(sum(x[cost_key] for x in candidate),2)<=budget:greedy=candidate
    baseline=dict(ids=[m['id'] for m in greedy],cost=round(sum(m[cost_key] for m in greedy),2),
                  utility=utility(benefits(greedy,p,hazard,benefit_scenario=benefit_scenario,mode=mode),WEIGHTS[priority]))
    rule_ids=[i for i in ['survey','valve','air-bricks'] if i in lookup]
    rule=[lookup[i] for i in rule_ids]
    while round(sum(m[cost_key] for m in rule),2)>budget and rule:rule.pop()
    rule_baseline=dict(ids=[m['id'] for m in rule],cost=round(sum(m[cost_key] for m in rule),2),utility=utility(benefits(rule,p,hazard,benefit_scenario=benefit_scenario,mode=mode),WEIGHTS[priority]))
    # Strategies are compared under the same declared priority, with explicit selection objectives.
    comparison=[]
    def compare(label,row,selection_basis):
        comparison.append(dict(name=label,ids=row['ids'],cost=row['cost'],cost_base=row['cost_base'],cost_high=row['cost_high'],budget_feasible_current=row['cost']<=budget,benefits=row['benefits'],utility=row['utility'],stability=stability(row),selection_basis=selection_basis,pareto_efficient=any(r['ids']==row['ids'] for r in nondominated)))
    def pick(cost_case,benefit_case,weights):
        pool=[r for r in all_rows if r['cost_'+cost_case]<=budget]
        return max(pool,key=lambda r:(utility(case_vectors[tuple(r['ids'])][benefit_case],weights),-r['cost_'+cost_case],tuple(r['ids'])))
    compare('Current assumptions',best(WEIGHTS[priority]),'Current selected cost/benefit assumptions')
    compare('Central optimum',pick('base','central',WEIGHTS[priority]),'Central costs and median group effects')
    compare('Conservative-cost optimum',pick('high','central',WEIGHTS[priority]),'High costs, central benefit; budget feasible at high costs')
    compare('Cautious-benefit optimum',pick('base','low',WEIGHTS[priority]),'Central costs and lower-quartile group effects')
    if robust_pool:compare('Minimax regret',robust,'Minimum maximum feasible-case regret across all nine assumptions, among every high-cost-affordable portfolio')
    compare('Energy-only',pick('base','central',(0,1,0)),'Gas-preference only, central costs and benefits; unknown savings excluded, not assumed zero')
    compare('Flood-pathways-only',pick('base','central',(1,0,0)),'Conditional pathway coverage only, not empirical damage reduction')
    for label,base in [('Cost-first greedy',baseline),('Fixed-priority sequence',rule_baseline)]:
        row=next(r for r in all_rows if set(r['ids'])==set(base['ids']))
        compare(label,row,'Simple baseline, evaluated under the same current priority weights')
    decisions = None
    if decision_intelligence:
        from .decision_intelligence import build_decisions
        decisions = build_decisions(p,hazard,budget,priority,scenario,benefit_scenario,
                                    all_rows,lookup,stability)
        packages = [dict(plan, cost_low=plan['costs']['low'], cost_base=plan['costs']['base'],
                         cost_high=plan['costs']['high'], objective_score=plan['utility'])
                    for plan in decisions['strategies']]
    for pack in packages:
        pack['measures']=[dict(lookup[i],why='Selected by exact constrained search for '+pack['name'].lower()+'. '+lookup[i]['rationale']) for i in pack['ids']]
        pack['remaining']=round(budget-pack['cost'],2)
        pack['high_cost_feasible']=pack['cost_high']<=budget
        pack['stability']=stability(pack)
        if decisions is None:
            pack['pareto_efficient']=any(r['ids']==pack['ids'] for r in nondominated)
        selected=[lookup[i] for i in pack['ids']]
        from .retrofit import decision_impact
        pack['gas_savings']=decision_impact(selected,p,benefit_scenario,hazard)
        from .pfr import coverage,recommendation
        pack['benefit_ledger']=dict(energy=dict(kind='Adjusted observational group scenario',estimate=pack['gas_savings']['central_kwh'],available=pack['gas_savings']['available']),carbon=pack['gas_savings'].get('carbon'),flood_empirical=dict(damage_reduction=None,kind='Not quantifiable from available transferable evidence'),flood_planning=coverage(selected,p,hazard,benefit_scenario),comfort=dict(score=pack['benefits'][2],kind='Assumed ordinal preference'),enabling_measures=[m['id'] for m in selected if m.get('category')=='Survey'],unquantified_energy=pack['gas_savings']['unquantified'])
        pack['benefit_sensitivity']={s:utility(benefits(selected,p,hazard,benefit_scenario=case,mode=mode),WEIGHTS[priority]) for s,case in [('lower','low'),('central','central'),('higher','high')]}
        for measure in pack['measures']:
            measure['evidence_ids']=['cost-'+measure['id'],'planning-utility']+(pack['gas_savings'].get('evidence_ids',[]) if measure['id'] in ['loft','wall','cavity'] else [])
            measure['why']+=' Eligibility was checked from the reported profile; required assessments and incompatible alternatives are enforced. Inclusion is conditional on a professional survey, not proof of personal effectiveness.'
            measure['flood_evidence']=recommendation(measure,p,hazard)
            if decisions is not None:
                from .quality import quality_record
                measure['quality_evidence'] = quality_record(measure)
            if measure['flood_evidence']:measure['evidence_ids']+=measure['flood_evidence']['evidence_ids']+['pfr-pathway-preference']
            if measure.get('category')=='Energy':
                from .applicability import assess as applicability
                measure['retrofit_applicability']=applicability([measure],p)
                measure['standalone_impact']=decision_impact([measure],p,benefit_scenario,hazard)
    result = dict(packages=packages,frontier=[dict(cost=r['cost'],utility=r['utility'],ids=r['ids']) for r in frontier],
                pareto_frontier=[dict(cost=r['cost'],cost_high=r['cost_high'],ids=r['ids'],benefits=r['benefits'],utility=r['utility']) for r in nondominated],
                stress_test=dict(scenarios=stress,unique_winners=len({tuple(s['ids']) for s in stress}),method='Exact re-optimisation across 3 cost × 3 benefit assumptions; no assigned probabilities'),
                strategy_comparison=comparison,feasible_count=len(rows),excluded=excluded,baseline=baseline,rule_baseline=rule_baseline,
                budget=budget,scenario=scenario,priority=priority, weights=WEIGHTS[priority],
                benefit_scenario=benefit_scenario,cost_overrides=overrides,evidence_mode=mode,
                method='Exact exhaustive binary search with dependencies, exclusions and saturating ordinal utility',
                benefit_unit='Preference utility: flood is conditional pathway-coverage preference (not damage reduction); comfort is an assumed ordinal proxy. Energy is a published group fraction applied to a reference or entered gas scenario, normalised to 2,000 kWh/year = 100 points (capped ±100). Unknown effects are excluded from the quantified objective, not interpreted as zero real benefit. Carbon is derived, not double-weighted. Weights and normalisation are preferences.')
    if decisions is not None:
        result['budget_decisions'] = decisions
    return result

def analyse(payload, *, adaptive=True):
    if not isinstance(payload,dict):raise ValueError('Expected a JSON object')
    if payload.get('evidence_mode','evidence')!='evidence':raise ValueError('Only evidence mode is served. The original version is preserved separately for comparison.')
    p=Property.parse(payload.get('property',{}))
    hazard=exposure(payload.get('lon',-1.08),payload.get('lat',53.95))
    hazard=dict(hazard,depth_evidence=exposure(payload.get('lon',-1.08),payload.get('lat',53.95),'depth_defended_100'))
    result=solve(p,hazard,payload.get('budget',10000),payload.get('priority','balanced'),payload.get('scenario','base'),payload.get('benefit_scenario','central'),payload.get('cost_overrides'),payload.get('evidence_mode','evidence'),decision_intelligence=adaptive)
    result['assessment']=assess(p,hazard)
    origin=payload.get('profile_origin','manual')
    if origin not in ['manual','demo']:raise ValueError('Unknown profile origin')
    result['assessment']['input_origin']='Synthetic demonstration profile' if origin=='demo' else 'User-provided manual inputs; not verified EPC data'
    result['property']=asdict(p)
    from .applicability import assess as applicability
    result['retrofit_applicability']={m['id']:applicability([m],p) for m in catalogue() if m['category']=='Energy'}
    if adaptive:
        from .decision_intelligence import professional_checks
        from .pfr import recommendation
        candidates=[]
        for measure in catalogue():
            reason=eligibility(p,measure,hazard)
            flood=recommendation(measure,p,hazard)
            impact=result['retrofit_applicability'].get(measure['id'])
            checks=professional_checks([measure],p,hazard)
            if reason:
                status=('Insufficient evidence' if measure['id']=='heat-pump' and measure['id'] not in p.completed_measures and p.heating!='heat-pump' and p.property_type!='flat'
                        else 'Survey required' if measure['id'] in {'wall','cavity'} and p.wall_type=='unknown' and not p.listed and p.property_type!='flat'
                        else 'Not suitable')
            elif measure['category']=='Survey':
                status='Applicable'
            elif impact and not impact['quantifiable']:
                status='Insufficient evidence'
            else:
                status='Conditionally applicable'
            candidates.append(dict(measure, status=status, reason=reason,
                                   professional_check=checks[0]['requirement'] if checks else None,
                                   evidence_type=flood['evidence_class'] if flood else
                                   'Published observational evidence' if impact and impact['quantifiable'] else 'Planning guidance',
                                   flood_evidence=flood,retrofit_applicability=impact))
        result['candidates']=candidates
    from .energy import predict
    result['energy_prediction']=predict(p) if hazard.get('coverage')!='outside' else dict(available=False,reason='Outside York pilot: the regional model context is not established.')
    if payload.get('energy_history') is not None:
        from .energy import predict_history
        if hazard.get('coverage')=='outside' or p.heating!='gas':
            result['history_prediction']=dict(available=False,reason='The historical scenario requires a gas profile inside the pilot.')
        else:result['history_prediction']=predict_history(payload['energy_history'],p)
    from .retrofit import consumption_baseline
    result['consumption_baseline']=consumption_baseline(
        p,hazard,payload.get('energy_history'),property_prediction=result['energy_prediction'],
        history_prediction=result.get('history_prediction'))
    result['flood_scenario']=exposure(payload.get('lon',-1.08),payload.get('lat',53.95),payload.get('flood_layer','rofrs'))
    result['depth_scenario']=exposure(payload.get('lon',-1.08),payload.get('lat',53.95),'depth_defended_100')
    from .climate import climate_context
    result['climate_context']=climate_context(payload.get('lon',-1.08),payload.get('lat',53.95),p)
    result['decision_basis']='Published adjusted NEED group impacts and explicitly stated scenario assumptions; the consumption model is supporting context only and is not used in portfolio rankings.'
    for pack in result['packages']:
        for measure in pack['measures']:
            if measure['category']=='Flood':
                measure['evidence_ids'].append('ea-rofrs')
                link=next((link for link in result['climate_context']['links'] if link['measure_id']==measure['id']),None)
                measure['hazard_link']=link
                if link:measure['why']+=' '+link['reason']
    return result
