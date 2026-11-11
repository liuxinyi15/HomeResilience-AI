"""Household choices and phased planning over the exact feasible set."""
import json
from dataclasses import asdict
from functools import lru_cache
from hashlib import sha256

from .pfr import coverage, recommendation
from .retrofit import decision_impact

COST_CASES = ('low', 'base', 'high')
UPGRADE_INCREMENTS = (500, 2000, 5000)
QUALITY_NOTE = ('There is insufficient comparable evidence to rank overall product quality. '
                'Compare certification for the exact configuration, installation fit, servicing, warranty '
                'and replacement terms before paying for a premium specification.')


def specification(measure):
    product = measure.get('product') or {}
    record = product.get('record', {})
    return (record.get('id'), measure.get('material_note'),
            product.get('reported_aperture_depth_m'))


def portfolio_signature(measures, assumptions):
    """Stable across ordering and display names. Include enabling scope and evidence inputs."""
    canonical = json.dumps(dict(
        scope=[dict(id=m['id'], specification=specification(m), requires=sorted(m['requires']),
                    allowances=[f"{m['cost_' + c]:.2f}" for c in COST_CASES], cost_origin=m.get('cost_origin'))
               for m in sorted(measures, key=lambda m: m['id'])],
        assumptions=assumptions), sort_keys=True, separators=(',', ':'), allow_nan=False)
    return sha256(canonical.encode()).hexdigest()


def decision_assumptions(p, hazard, scenario, benefit_case):
    profile = asdict(p)
    profile['existing_protection'] = sorted(profile['existing_protection'])
    return dict(property=profile, exposure=hazard.get('category'), coverage=hazard.get('coverage'),
                depth=hazard.get('depth_evidence'), cost_case=scenario, benefit_case=benefit_case)


def cost_breakdown(before, after):
    old = {m['id']: m for m in before['measures']}
    new = {m['id']: m for m in after['measures']}
    cost_key = 'cost_' + after['cost_scenario']
    rows = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        start = a[cost_key] if a else None
        end = b[cost_key] if b else None
        sa, sb = specification(a or {}), specification(b or {})
        status = ('added' if not a else 'removed' if not b else 'specification_changed'
                  if sa != sb else 'cost_changed' if start != end else 'retained')
        rows.append(dict(id=key, name=(b or a)['name'], status=status, before_gbp=start,
                         after_gbp=end, delta_gbp=round((end or 0) - (start or 0), 2),
                         cost_range_delta={c: round((b['cost_' + c] if b else 0)
                                                    - (a['cost_' + c] if a else 0), 2)
                                           for c in COST_CASES},
                         before_configuration=sa[0], after_configuration=sb[0],
                         before_product=((a or {}).get('product') or {}).get('record', {}).get('name'),
                         after_product=((b or {}).get('product') or {}).get('record', {}).get('name'),
                         before_material=sa[1], after_material=sb[1],
                         before_depth_m=sa[2], after_depth_m=sb[2]))
    return rows


def incremental(before, after):
    a, b = (p['gas_savings'] for p in (before, after))
    old, new = (set(p['pathways']['covered']) for p in (before, after))
    comparable = a['available'] and b['available']
    return dict(extra_gbp=round(after['cost'] - before['cost'], 2),
                cost_range={c: round(after['costs'][c] - before['costs'][c], 2) for c in COST_CASES},
                energy_kwh=round(b['central_kwh'] - a['central_kwh'], 1) if comparable else None,
                carbon_kg=round(b['carbon']['central_kg_co2e'] - a['carbon']['central_kg_co2e'], 1) if comparable else None,
                energy_cohorts=dict(before=a.get('group'), after=b.get('group')),
                energy_evidence=dict(before=a.get('evidence_ids', []), after=b.get('evidence_ids', [])),
                pathways_gained=sorted(new - old), pathways_lost=sorted(old - new),
                comfort_points=round(after['benefits'][2] - before['benefits'][2], 3),
                measures=cost_breakdown(before, after))


def outcome_classes(plan):
    return dict(energy='published_modelled' if plan['gas_savings']['available'] else 'unavailable',
                carbon='published_modelled' if plan['gas_savings']['available'] else 'unavailable',
                flood_pathways='engineering_assumption', comfort='planning_preference',
                flood_damage_reduction='unavailable', lifecycle='illustrative'
                if (plan.get('lifecycle') or {}).get('totals_gbp') is not None else 'unavailable')


def dominates(a, b):
    """Compare on allowance, declared benefits, pathway identity and risk-screen tier."""
    def objective(row):
        return (-row['cost_low'], -row['cost_base'], -row['cost_high'], row['risk_tier'], *row['benefits'])

    x, y = objective(a), objective(b)
    return (a['covered'] >= b['covered'] and all(i >= j for i, j in zip(x, y))
            and (x != y or a['covered'] != b['covered']))


def decision_frontier(rows):
    return [row for row in rows if not any(dominates(other, row) for other in rows)]


def meaningfully_different(a, b):
    """A scope change must change a decision dimension. Price alone is insufficient."""
    if a['portfolio_signature'] == b['portfolio_signature']:
        return False
    if a['pathways']['covered'] != b['pathways']['covered']:
        return True
    if set(a['ids']) != set(b['ids']):
        return (a['risk_tier'] != b['risk_tier'] or a['benefits'][1:] != b['benefits'][1:]
                or a['high_cost_feasible'] != b['high_cost_feasible']
                or a['gas_savings'].get('evidence_ids') != b['gas_savings'].get('evidence_ids')
                or a['gas_savings']['available'] != b['gas_savings']['available'])
    # Unverified free-text material and price changes alone cannot establish a strategy.
    def certified_scope(plan):
        return {m['id']: specification(m)[0] for m in plan['measures']
                if (m.get('product') or {}).get('eligible') and specification(m)[0]}
    return certified_scope(a) != certified_scope(b)


def professional_checks(measures, p, hazard):
    checks = []
    for measure in measures:
        flood = recommendation(measure, p, hazard)
        if flood:
            requirement = flood['record']['prerequisites']
        elif measure['category'] == 'Energy':
            requirement = 'Verify existing fabric, ventilation, moisture, installation scope and permissions.'
        elif measure['category'] == 'Survey':
            requirement = measure['rationale']
        else:
            continue
        checks.append(dict(id=measure['id'], requirement=requirement))
    return checks


def explanation(plan, cheaper, basis, checks):
    delta = incremental(cheaper, plan) if cheaper else None
    if delta:
        added = [f"{r['name']} (£{r['after_gbp']:,.2f})" for r in delta['measures'] if r['status'] == 'added']
        removed = [r['name'] for r in delta['measures'] if r['status'] == 'removed']
        changes = []
        if added:
            changes.append('Adds ' + ', '.join(added) + '.')
        if removed:
            changes.append('Leaves out ' + ', '.join(removed) + '.')
        if delta['pathways_gained']:
            changes.append('Conditional coverage added for ' + ', '.join(delta['pathways_gained']) + '.')
        if delta['pathways_lost']:
            changes.append('Conditional coverage dropped for ' + ', '.join(delta['pathways_lost']) + '.')
        gas = delta['energy_kwh']
        changes.append('The change in the published group gas scenario is unknown.' if gas is None
                       else f'Published group gas scenario changes by {gas:+,.1f} kWh/year.')
        if delta['comfort_points']:
            changes.append('The selected measures also change the comfort planning preference.')
        sufficient = ('Choose the cheaper plan if its listed scope meets your immediate needs and '
                      'you can defer the added work described here.')
        if cheaper['high_cost_feasible'] and not plan['high_cost_feasible']:
            sufficient += ' The cheaper plan also fits at higher allowances.'
    else:
        changes = ['There is no distinct cheaper recommendation in this set.']
        sufficient = 'Confirm which work is needed and hold unused funds for survey findings and scoped quotes.'
    return dict(why=basis, cheaper_alternative=dict(ids=cheaper['ids'], cost=cheaper['cost']) if cheaper else None,
                why_not_cheaper=' '.join(changes), extra_budget=delta, when_another_is_better=sufficient,
                when_to_prioritise_quality=QUALITY_NOTE, professional_verification=checks,
                uncertainties=['Conditional flood coverage depends on survey findings and installation.',
                               'Household damage reduction and realised energy savings are unknown.'])


def build_decisions(p, hazard, budget, priority, scenario, benefit_case, all_rows, lookup, stability):
    """Use property-specific risk and higher allowances instead of fixed budget bands."""
    remaining = coverage([], p, hazard)['remaining_relevant']
    risk_screen = hazard.get('category') in {'High', 'Medium'} and priority != 'energy' and bool(remaining)
    openings_relevant = 'openings' in remaining
    rows = []
    seen = set()
    assumptions = decision_assumptions(p, hazard, scenario, benefit_case)
    for row in all_rows:
        ids = row['ids']
        measures = [lookup[i] for i in ids]
        signature = portfolio_signature(measures, assumptions)
        if signature in seen:
            continue
        seen.add(signature)
        tier = 0
        if risk_screen and ('survey' in ids or 'survey' in p.completed_measures):
            tier = 2 if openings_relevant and {'barrier', 'flood-door'}.intersection(ids) else 1
        rows.append(dict(row, risk_tier=tier, portfolio_signature=signature,
                         covered=set(coverage(measures, p, hazard, benefit_case)['covered'])))

    @lru_cache(maxsize=None)
    def summary(signature):
        row = indexed[signature]
        measures = [lookup[i] for i in row['ids']]
        return dict(name='', ids=row['ids'], cost=row['cost'], utility=row['utility'], risk_tier=row['risk_tier'],
                    benefits=row['benefits'], measures=measures, cost_scenario=scenario,
                    portfolio_signature=signature, costs={c: row['cost_' + c] for c in COST_CASES},
                    high_cost_feasible=row['cost_high'] <= budget,
                    pathways=coverage(measures, p, hazard, benefit_case),
                    gas_savings=decision_impact(measures, p, benefit_case, hazard))

    def describe(row):
        return summary(row['portfolio_signature'])

    def order(row):
        return row['utility'], -row['cost'], -row['cost_high'], tuple(row['ids'])

    indexed = {r['portfolio_signature']: r for r in rows}
    frontier = decision_frontier([r for r in rows if r['cost'] <= budget])
    tier = max(r['risk_tier'] for r in frontier)
    candidates = [r for r in frontier if r['risk_tier'] == tier]
    balanced = max(candidates, key=order)
    robust = [r for r in frontier if r['cost_high'] <= budget]
    value_pool = [r for r in candidates if r['cost_high'] <= budget] or candidates
    # A £1 denominator floor stabilises zero and nominal-cost bundles. Use the higher allowance.
    value = max(value_pool, key=lambda r: (r['utility'] / max(1, r['cost_high']), *order(r)))
    risk_priority = {2: 'opening_pathway', 1: 'flood_survey'}.get(tier)
    if risk_screen and tier == 0 and 'survey' in lookup:
        risk_priority = 'survey_over_budget'
    risk_text = {
        'opening_pathway': 'Your mapped exposure and reported openings make a flood survey and conditional opening protection a priority.',
        'flood_survey': 'Start with a flood survey. The selected allowances and property checks limit opening protection options.',
        'survey_over_budget': 'The flood survey exceeds this budget. Check official warnings and make a household flood plan while confirming a survey quote.',
    }.get(risk_priority, 'Plans reflect your reported home, existing protection and selected priorities.')

    choices = [('recommended_balance', 'Recommended Balance', balanced,
                'Addresses the most under your selected priorities and current allowances. ' + risk_text)]
    if meaningfully_different(describe(value), describe(balanced)):
        choices.append(('best_value', 'Best Value', value,
                        'Prioritises benefit per pound at the higher allowance while retaining the applicable risk priorities. '
                        + ('It fits at higher allowances.' if value['cost_high'] <= budget
                           else 'Check the quote before committing because higher allowances exceed your budget.')))
    if balanced['cost_high'] > budget and robust:
        robust_tier = max(r['risk_tier'] for r in robust)
        # Keep the strongest flood preparation affordable under the stress case.
        fallback = min((r for r in robust if r['risk_tier'] == robust_tier),
                       key=lambda r: (stability(r)['max_regret'], -r['utility'], r['cost_high'], tuple(r['ids'])))
        if all(meaningfully_different(describe(fallback), describe(r)) for _, _, r, _ in choices):
            choices.append(('cost_robust', 'Cost-Robust', fallback,
                            'Fits at higher allowances and stays closest to the tested preference optima among plans that meet its risk screen. '
                            'Check the scope differences below.'))

    strategies = []
    for key, title, row, basis in choices:
        plan = dict(describe(row), name=title)
        cheaper = max((r for _, _, r, _ in choices if r['cost'] < row['cost']), key=order, default=None)
        checks = professional_checks(plan['measures'], p, hazard)
        plan.update(key=key, remaining_gbp=round(budget - row['cost'], 2), evidence_classes=outcome_classes(plan),
                    stability=stability(row), pareto_efficient=True, lifecycle_cost_gbp=None,
                    explanation=explanation(plan, describe(cheaper) if cheaper else None, basis, checks))
        plan.pop('measures')
        strategies.append(plan)

    upgrades = {key: upgrade_path(row, rows, budget, describe, order) for key, _, row, _ in choices}
    balance_path = upgrades['recommended_balance']
    if not any(balance_path[k] for k in ('next_add_only', 'next_replacement')):
        balance_path['spending_note'] = ('A higher budget buys no further improvement under the current priorities '
                                         'and catalogue. Keep unused funds for quotes and survey findings.')
    survey = lookup.get('survey') if risk_priority else None
    return dict(version='decision-intelligence-v2', strategies=strategies, risk_priority=risk_priority,
                risk_explanation=risk_text, flood_survey_cost_gbp=survey and survey['cost_' + scenario],
                upgrades=upgrades, next_add_only_upgrade=upgrades['recommended_balance']['next_add_only'],
                alternatives_note=('One distinct recommendation meets the selection criteria for this home and budget.'
                                   if len(strategies) == 1 else None),
                method=dict(best_value='Preference points divided by the higher allowance, with a £1 denominator floor.',
                            recommended_balance='Maximum selected preference utility at the strongest affordable risk tier.',
                            cost_robust='Minimum worst-case preference regret among distinct high-cost-affordable options at their strongest affordable risk tier.',
                            frontier='Conditional pathway set, risk tier, energy and comfort preferences, and all three cost allowances.'),
                quality_status='insufficient_comparable_evidence', quality_note=QUALITY_NOTE,
                lifecycle_note='Lifecycle cost cannot yet be compared reliably without a complete installed scope, servicing and replacement costs.')


def upgrade_path(current, rows, budget, describe, order):
    ids = set(current['ids'])
    baseline = describe(current)
    improvements = [r for r in rows if r['cost'] <= 100000 and r['risk_tier'] >= current['risk_tier']
                    and r['utility'] > current['utility'] and meaningfully_different(baseline, describe(r))]
    add_only = [r for r in improvements if ids < set(r['ids'])]
    replacement = [r for r in improvements if ids - set(r['ids'])]

    def step(row, limit, kind):
        if row is None:
            return None
        plan = describe(row)
        new = set(row['ids'])
        delta = incremental(baseline, plan)
        required = {i for m in plan['measures'] if m['id'] in new - ids for i in m['requires']}
        return dict(kind=kind, ids=row['ids'], cost=row['cost'], cost_high=row['cost_high'],
                    budget_required=row['cost'], extra_budget_gbp=round(max(0, row['cost'] - budget), 2),
                    retained=sorted(ids & new), removed=sorted(ids - new), added=sorted(new - ids),
                    new_dependencies=sorted(required - ids), retained_dependencies=sorted(required & ids),
                    high_cost_feasible=row['cost_high'] <= limit, delta=delta,
                    preference_gain=round(row['utility'] - current['utility'], 4),
                    phase_cost_note='The cost difference compares whole-plan allowances. Ask for a phased quote covering repeat visits, removal and making good.')

    def best(pool, limit, minimum_utility):
        return max((r for r in pool if r['cost'] <= limit and r['utility'] > minimum_utility),
                   key=order, default=None)

    def next_step(pool, kind):
        threshold = min((r['cost'] for r in pool if r['cost'] > budget), default=None)
        return (step(max((r for r in pool if r['cost'] == threshold), key=order), threshold, kind)
                if threshold is not None else None)

    scenarios = []
    # Carry each add-only milestone into the next search. A previous milestone stays
    # available if spending more cannot improve it while retaining that work.
    phase = current
    for increment in UPGRADE_INCREMENTS:
        limit = min(100000, budget + increment)
        addition = best([r for r in add_only if set(phase['ids']) <= set(r['ids'])], limit, phase['utility'])
        if addition:
            phase = addition
        add = phase if phase is not current else None
        swap = best(replacement, limit, phase['utility'])
        if swap:
            reason = 'The replacement gains more under your preferences. Check the work and coverage you would lose.'
        elif addition:
            reason = 'This addition fits and improves the starting plan while keeping the work already selected.'
        elif add:
            reason = 'The earlier add-only milestone still fits. More spending buys no further qualifying improvement here.'
        else:
            reason = 'No distinct improvement fits this allowance while meeting the current risk priorities.'
        scenarios.append(dict(increase_gbp=increment, budget=limit,
                              add_only=step(add, limit, 'add_only'),
                              reoptimised=step(swap, limit, 'replacement'), reason=reason))
    return dict(next_add_only=next_step(add_only, 'add_only'),
                next_replacement=next_step(replacement, 'replacement'), scenarios=scenarios)
