"""Editable portfolios evaluated by the production v4 benefit and exact search engines."""
import copy
import json
from dataclasses import asdict
from .decision_intelligence import (incremental, outcome_classes, portfolio_signature,
                                    professional_checks, specification, decision_assumptions, QUALITY_NOTE)
from pathlib import Path
from .engine import Property, catalogue, exposure, eligibility, valid_subset, benefits, utility, WEIGHTS, solve
from .retrofit import consumption_baseline, decision_impact, survey_checks
from .pfr import coverage, recommendation, depth_context
from .quality import quality_source, quality_record, lifecycle_cost

ROOT = Path(__file__).resolve().parents[2]

def product_evidence():
    result=json.loads((ROOT/'data/processed/product-evidence.json').read_text())
    result['quality_version']=quality_source()['version']
    for product in result['products']:
        product['quality']=quality_record(None,product)
    return result

def product_check(record, measure_id, p, hazard):
    """Fail closed on scope/depth; listing never establishes whole-property suitability."""
    reasons=[]
    if measure_id not in record['measure_ids']: reasons.append('Certified configuration is outside this measure scope.')
    if record['application']!='domestic_opening': reasons.append('This configuration is for a kiosk, outside domestic retrofit scope.')
    if record['standard']!='BS 851188-1' or not record.get('certificate'): reasons.append('Required certification evidence is absent.')
    depth=depth_context(p,hazard)
    # DMWD datum is the certified aperture threshold. Area/ground-level depth cannot be equated to it.
    return dict(eligible=not reasons, status='ineligible' if reasons else 'conditional_on_design', reasons=reasons,
                depth_context=depth, dmwd_m=record['dmwd_m'],
                requirements=['Installer must verify the exact certified size, opening direction, threshold datum, installation and current certificate scope.',
                              'A surveyed aperture-relative water depth must not exceed the certified DMWD. Ground-floor and area depths are not automatically comparable.'],
                evidence_class='Certified laboratory specification; no household loss or energy effect',record=record)

def compare(payload):
    if not isinstance(payload,dict): raise ValueError('Expected a JSON object')
    p=Property.parse(payload.get('property',{}))
    hazard=dict(exposure(payload.get('lon',-1.08),payload.get('lat',53.95)),
                depth_evidence=exposure(payload.get('lon',-1.08),payload.get('lat',53.95),'depth_defended_100'))
    baseline_context=consumption_baseline(p,hazard,payload.get('energy_history'))
    plans=payload.get('plans')
    if not isinstance(plans,list) or not 1<=len(plans)<=4: raise ValueError('Compare one to four plans')
    budget=payload.get('budget',10000);priority=payload.get('priority','balanced')
    scenario=payload.get('scenario','base');benefit_case=payload.get('benefit_scenario','central')
    evidence=product_evidence()
    products={r['id']:r for r in evidence['products']};lookup={m['id']:m for m in catalogue()}
    baseline=payload.get('baseline_index',0)
    if type(baseline) is not int or not 0<=baseline<len(plans):raise ValueError('Invalid baseline plan')
    results=[]
    benchmarks={}
    assumptions=decision_assumptions(p,hazard,scenario,benefit_case)
    for plan in plans:
        if not isinstance(plan,dict) or set(plan)-{'name','ids','cost_overrides','products','materials','depths','retrofit_physics','lifecycle'}: raise ValueError('Unknown plan fields')
        name=plan.get('name','Custom plan');ids=plan.get('ids',[])
        if not isinstance(name,str) or not 1<=len(name.strip())<=80: raise ValueError('Plan name must be 1–80 characters')
        if not isinstance(ids,list) or any(type(i) is not str or i not in lookup for i in ids) or len(set(ids))!=len(ids): raise ValueError('Unknown or duplicate measure IDs')
        survey=survey_checks(plan.get('retrofit_physics',{}))
        if set(survey)-set(ids):raise ValueError('Physics checks must belong to selected measures')
        choices=plan.get('products',{});materials=plan.get('materials',{});depths=plan.get('depths',{})
        if not all(isinstance(d,dict) and not set(d)-set(ids) for d in [choices,materials,depths]): raise ValueError('Options must belong to selected measures')
        if any(type(v) is not str or len(v)>200 for v in materials.values()): raise ValueError('Material notes must be at most 200 characters')
        if any(type(v) is not str or v not in products for v in choices.values()): raise ValueError('Unknown certified product')
        for key,v in depths.items():
            import math
            if key not in choices or type(v) not in (float,int) or not math.isfinite(v) or not 0<=v<=5: raise ValueError('Product aperture depths must be finite, 0–5m')
        quotes=plan.get('cost_overrides',{})
        if not isinstance(quotes,dict) or set(quotes)-set(ids): raise ValueError('Quotes must belong to selected measures')
        # Production optimiser validates quote ranges, budget, scenarios, and preferences.
        quote_key=json.dumps(quotes,sort_keys=True,allow_nan=False)
        if quote_key not in benchmarks:
            benchmarks[quote_key]=solve(p,hazard,budget,priority,scenario,benefit_case,quotes)
        benchmark=benchmarks[quote_key]
        selected=copy.deepcopy([lookup[i] for i in ids]);issues=[];checks={}
        for m in selected:
            i=m['id'];reason=eligibility(p,m,hazard)
            if reason:issues.append(i+': '+reason)
            m['eligibility_reason']=reason
            for k,v in quotes.get(i,{}).items():m['cost_'+k]=round(v,2)
            m['cost_origin']='User quotation; scope, VAT and installation unverified' if i in quotes else m['cost_origin']
            m['material_note']=(materials.get(i) or '').strip() or None
            m['material_effect']='User scope note only; no material-specific thermal, carbon or flood performance asserted' if m['material_note'] else None
            if i in choices:
                c=product_check(products[choices[i]],i,p,hazard)
                if i in depths:
                    c['reported_aperture_depth_m']=depths[i]
                    if c['dmwd_m'] is not None and depths[i]>c['dmwd_m']:
                        c['eligible']=False;c['status']='ineligible';c['reasons'].append('Reported aperture-relative depth exceeds certified DMWD.')
                else:c['requirements'].append('Aperture-relative design depth has not been supplied.')
                checks[i]=c
                if not c['eligible']:issues.extend(i+': '+s for s in c['reasons'])
                m['product']=c
                m['cost_origin']+='; generic measure allowance, NOT a product price' if i not in quotes else '; quotation linked to selected product'
            m['flood_evidence']=recommendation(m,p,hazard)
            m['quality_evidence']=products[choices[i]]['quality'] if i in choices else quality_record(m)
            if i in quotes:
                m['cost_evidence_class']='illustrative' if payload.get('profile_origin')=='demo' else 'reported_quote'
            else:
                m['cost_evidence_class']='published_modelled' if i in {'loft','cavity'} else 'illustrative'
            m['evidence_ids']=['cost-'+i,'planning-utility']+(m['flood_evidence']['evidence_ids'] if m['flood_evidence'] else [])
            if m['category']=='Energy':
                from .applicability import assess
                m['retrofit_applicability']=assess([m],p)
                m['standalone_impact']=decision_impact([m],p,benefit_case,hazard,eligibility_reason=reason,survey=survey)
        if not valid_subset(selected, p.completed_measures):
            for m in selected:
                missing=set(m['requires'])-set(ids)-set(p.completed_measures);excluded=set(m['excludes'])&(set(ids)|set(p.completed_measures))
                if missing:issues.append(m['id']+': requires '+', '.join(sorted(missing)))
                if excluded:issues.append(m['id']+': incompatible with '+', '.join(sorted(excluded)))
        costs={k:round(sum(m['cost_'+k] for m in selected),2) for k in ['low','base','high']}
        structurally_feasible=not issues
        if costs[scenario]>budget:issues.append('Selected cost scenario exceeds budget.')
        feasible=not issues
        # Rejected product configurations cannot acquire pathway credit.
        screened=[m for m in selected if not m['eligibility_reason'] and checks.get(m['id'],{'eligible':True})['eligible']]
        gas=decision_impact(screened,p,benefit_case,hazard,survey=survey)
        for m in selected:
            if m['id'] in ['loft','cavity','wall']:m['evidence_ids']+=gas.get('evidence_ids',[])
        vector=benefits(screened,p,hazard,benefit_scenario=benefit_case)
        stress=[]
        for case in benchmark['stress_test']['scenarios']:
            affordable=costs[case['cost_case']]<=budget
            value=utility(benefits(screened,p,hazard,benefit_scenario=case['benefit_case']),WEIGHTS[priority])
            stress.append(dict(cost_case=case['cost_case'],benefit_case=case['benefit_case'],feasible=affordable and structurally_feasible,cost=costs[case['cost_case']],utility=value if affordable and structurally_feasible else None,selected_again=affordable and structurally_feasible and set(ids)==set(case['ids']),
                               generic_benchmark_gap=round(max(0,case['utility']-value),4) if affordable and structurally_feasible else None))
        results.append(dict(name=name,ids=ids,measures=selected,feasible=feasible,issues=issues,costs=costs,cost=costs[scenario],cost_scenario=scenario,
                            portfolio_signature=portfolio_signature(selected, dict(
                                assumptions, retrofit_physics=survey, lifecycle=plan.get('lifecycle', {}))),
                            professional_checks=professional_checks(selected,p,hazard)+[
                                dict(id=i,requirement=check) for i,c in checks.items() for check in c['requirements']],
                            lifecycle=lifecycle_cost(plan.get('lifecycle',{}),costs),
                            gas_savings=gas,pathways=coverage(screened,p,hazard,benefit_case),benefits=vector,
                            utility=utility(vector,WEIGHTS[priority]) if feasible else None,stress=stress,
                            benchmark_scope=quotes,
                            benchmark=dict(ids=benchmark['packages'][0]['ids'],utility=benchmark['packages'][0]['utility'],
                                           interpretation='Generic measure optimum under this plan’s quotes. Product-specific design restrictions may tighten feasibility; this is an upper benchmark, not a certified-product optimum.'),
                            assumptions=['All eligible measures remain conditional on professional survey and permissions.',
                                         'Changing a product or material does not invent a new measured effect. NEED effects refer to installation cohorts, not brands.',
                                         'Quoted ranges are scope assumptions, not statistical confidence intervals.']))
    for plan in results:
        gaps=[s['generic_benchmark_gap'] for s in plan['stress'] if s['generic_benchmark_gap'] is not None]
        plan['stability']=dict(feasible_cases=sum(s['feasible'] for s in plan['stress']),total_cases=9,max_regret=max(gaps) if gaps else None,selected_again=sum(s['selected_again'] for s in plan['stress']),interpretation='Non-probabilistic scenarios. Regret and selection matches use the generic-measure benchmark under this plan’s quotations, not certified-product optimality.')
        plan['difference']=None
        plan['evidence_classes']=outcome_classes(plan)
    for plan in results:plan['difference']=plan_difference(results[baseline],plan)
    scenarios=[]
    for index in range(9):
        entries=[dict(plan_index=i,**r['stress'][index]) for i,r in enumerate(results)]
        scores=sorted({r['utility'] for r in entries if r['feasible']},reverse=True)
        for entry in entries:entry['rank']=scores.index(entry['utility'])+1 if entry['feasible'] else None
        scenarios.append(dict(cost_case=entries[0]['cost_case'],benefit_case=entries[0]['benefit_case'],plans=entries))
    for i,plan in enumerate(results):
        plan['dominated_by']=[j for j,other in enumerate(results) if j!=i and other['feasible'] and plan['feasible'] and other['cost']<=plan['cost'] and all(a>=b for a,b in zip(other['benefits'],plan['benefits'])) and (other['cost']<plan['cost'] or other['benefits']!=plan['benefits'])]
        plan['action_package']=action_package(plan,budget) if plan['feasible'] else None
    chosen=payload.get('selected_index')
    if chosen is not None and (type(chosen) is not int or not 0<=chosen<len(results)):raise ValueError('Invalid selected plan')
    selected=action_package(results[chosen],budget) if chosen is not None else None
    return dict(property=asdict(p),budget=budget,scenario=scenario,benefit_scenario=benefit_case,baseline_index=baseline,selected_index=chosen,selected_package=selected,plans=results,scenario_comparison=scenarios,consumption_baseline=baseline_context,
                evidence=evidence,method='Production savings, pathway coverage, eligibility, constraints and exact optimisation.')



def plan_difference(base, alternative):
    """Deterministic accounting and evidence deltas; no inferred causal mechanisms."""
    before={m['id']:m for m in base['measures']};after={m['id']:m for m in alternative['measures']}
    shared=sorted(before.keys() & after.keys());added=sorted(after.keys()-before.keys());removed=sorted(before.keys()-after.keys())
    replacements=[]
    for i in shared:
        old=before[i];new=after[i]
        a=old.get('product',{}).get('record',{});b=new.get('product',{}).get('record',{})
        if specification(old) != specification(new):
            replacements.append(dict(id=i,from_configuration=a.get('id'),to_configuration=b.get('id'),
                                     from_depth_m=specification(old)[2],to_depth_m=specification(new)[2],from_product=a.get('name','Generic specification'),to_product=b.get('name','Generic specification'),from_material=old.get('material_note'),to_material=new.get('material_note'),direct_substitute=a.get('measure_ids')==b.get('measure_ids') if a and b else None,
                                     limitation='Exact aperture fit, dimensions and installation remain design checks; identical pathway scope does not prove interchangeability.'))
    delta = incremental(base, alternative)
    breakdown = delta['measures']
    cost_changes = [dict(id=r['id'], name=r['name'], delta=r['delta_gbp']) for r in breakdown if r['delta_gbp']]
    lost, gained = delta['pathways_lost'], delta['pathways_gained']
    a_cases = {case for case, stress in enumerate(base['stress']) if stress['feasible']}
    b_cases = {case for case, stress in enumerate(alternative['stress']) if stress['feasible']}
    comparable_regret = a_cases == b_cases and bool(a_cases) and base['benchmark_scope'] == alternative['benchmark_scope']
    d = dict(cost=delta['extra_gbp'], cost_range=delta['cost_range'], added=added, removed=removed,
             in_both=shared, replacements=replacements, cost_changes=cost_changes,
             energy_kwh=delta['energy_kwh'], carbon_kg=delta['carbon_kg'],
             energy_cohorts=delta['energy_cohorts'], energy_evidence=delta['energy_evidence'],
             pathways_lost=lost, pathways_gained=gained,
             feasibility=dict(before=base['feasible'], after=alternative['feasible'],
                              new_issues=sorted(set(alternative['issues'])-set(base['issues'])),
                              resolved_issues=sorted(set(base['issues'])-set(alternative['issues']))),
             robustness=dict(feasible_cases=len(b_cases)-len(a_cases),
                             higher_cost_feasible_before=all(i in a_cases for i in range(6,9)),
                             higher_cost_feasible_after=all(i in b_cases for i in range(6,9)),
                             worst_feasible_regret=round(alternative['stability']['max_regret']-
                                                        base['stability']['max_regret'],4)
                             if comparable_regret else None))
    explanations=[]
    if cost_changes:
        explanations.append('Cost changes are accounted for by '+ '; '.join(f"{r['name']}: {r['delta']:+,.2f} GBP" for r in cost_changes)+'. Compare the scope changes alongside the price.')
    else:explanations.append('Total cost is unchanged under the selected allowance.')
    if lost:explanations.append('Pathways no longer addressed: '+', '.join(lost)+'. This is conditional coverage, not measured damage reduction.')
    if gained:explanations.append('Additional pathways addressed: '+', '.join(gained)+'. Survey confirmation is still required.')
    if not lost and not gained:explanations.append('Conditional flood coverage is unchanged.')
    if d['energy_kwh'] is None:explanations.append('Energy and carbon differences are unknown because at least one plan lacks applicable published evidence; unknown is not zero.')
    elif d['energy_kwh']==0:explanations.append('The published NEED gas scenario and derived direct-gas carbon scenario are unchanged.')
    else:explanations.append('The changed insulation portfolio changes the applicable published NEED scenario. It is population-level observational evidence, not an individual causal prediction.')
    if replacements:explanations.append('Product/material specifications changed. No manufacturer-specific energy or damage benefit is inferred; products for different openings are not direct substitutes.')
    explanations.extend(alternative['issues'])
    d['explanations']=explanations
    d['measure_breakdown']=breakdown
    d['comfort_preference_points']=round(alternative['benefits'][2]-base['benefits'][2],3)
    a,b=base['lifecycle'],alternative['lifecycle']
    comparable_lifecycle = (a['totals_gbp'] is not None and b['totals_gbp'] is not None
                            and all(a['inputs'][k] == b['inputs'][k] for k in ('years', 'discount_rate_pct')))
    d['lifecycle_gbp'] = round(b['totals_gbp'][alternative['cost_scenario']] -
                               a['totals_gbp'][base['cost_scenario']], 2) if comparable_lifecycle else None
    d['lifecycle_inputs'] = dict(before=a['inputs'], after=b['inputs'])
    d['quality_changes'] = [dict(id=i, before=(before.get(i) or {}).get('quality_evidence'),
                                 after=(after.get(i) or {}).get('quality_evidence'))
                            for i in sorted(before.keys() | after.keys())
                            if (before.get(i) or {}).get('quality_evidence') != (after.get(i) or {}).get('quality_evidence')]
    d['professional_checks'] = alternative['professional_checks']
    d['evidence_classes'] = dict(before=base['evidence_classes'], after=alternative['evidence_classes'])
    cheaper, dearer = (base, alternative) if d['cost'] >= 0 else (alternative, base)
    extra_scope = [m['name'] for m in dearer['measures'] if m['id'] not in cheaper['ids']]
    cheaper_test = None
    if d['cost'] and cheaper['feasible'] and dearer['feasible']:
        if extra_scope:
            cheaper_test = (f"Choose {cheaper['name']} if you can defer " + ', '.join(extra_scope)
                            + ' and its remaining scope meets your survey findings.')
        elif replacements:
            cheaper_test = (f"Choose {cheaper['name']} if its specification fits the survey and its "
                            'documented installation and servicing terms meet your needs.')
        else:
            cheaper_test = (f"Choose {cheaper['name']} if the installer confirms both prices cover the same work, "
                            'installation and VAT.')
    d['decision'] = dict(
        what_changes=' '.join(explanations),
        when_cheaper_suffices=cheaper_test,
        quality=QUALITY_NOTE,
        uncertainty='Confirm design, permissions, installed scope and service requirements. Household outcomes remain unknown.')
    d['evidence_ids']=sorted({e for m in base['measures']+alternative['measures'] for e in m.get('evidence_ids',[])})
    return d


def action_package(plan,budget):
    """Only a recomputed feasible plan may feed an executable, conditional roadmap."""
    if not plan['feasible']:raise ValueError('Infeasible custom plan cannot be selected: '+'; '.join(plan['issues']))
    result=copy.deepcopy({k:v for k,v in plan.items() if k!='action_package'})
    result.update(cost_low=plan['costs']['low'],cost_base=plan['costs']['base'],cost_high=plan['costs']['high'],remaining=round(budget-plan['cost'],2),custom=True,
                  benefit_ledger=dict(energy=plan['gas_savings'],carbon=plan['gas_savings'].get('carbon'),flood_planning=plan['pathways'],flood_empirical=dict(damage_reduction=None)),
                  implementation_stages=[dict(stage=stage,ids=[m['id'] for m in plan['measures'] if (m['category']=='Survey')==survey]) for stage,survey in [('Survey and permissions',True),('After survey: installation and commissioning',False)]])
    for m in result['measures']:
        m['why']='Selected in your custom comparison plan. '+m['rationale']+' All work remains conditional on survey and permissions.'
    return result
