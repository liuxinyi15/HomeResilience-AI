"""Evidence contract for retrofit decisions and an independent survey scenario."""
import math

from .energy import predict, predict_history
from .impacts import NAMES, evidence, group_for, savings

VERSION = 'retrofit-impact-v1'
FABRIC = frozenset(NAMES)
PHYSICS_SOURCE = 'https://www.gov.uk/government/publications/green-homes-grant-ghg-smeter-project-evaluation'
PHYSICS_FIELDS = ('htc_before_w_per_k', 'htc_after_w_per_k', 'heating_degree_days_k_days',
                  'efficiency_before', 'efficiency_after', 'survey_source')


def consumption_baseline(p, hazard, history=None, *, property_prediction=None, history_prediction=None):
    """Separate consumption context. Published effect transfer uses its own stated denominator."""
    if hazard.get('coverage') == 'outside' or p.heating != 'gas':
        return dict(kind='unknown', estimate_kwh=None, interval_kwh=None,
                    limitation='Gas consumption context requires a gas profile inside the York pilot.')
    if p.annual_gas_kwh is not None:
        return dict(kind='reported_annual_gas', estimate_kwh=p.annual_gas_kwh, interval_kwh=None,
                    limitation='Use a recent complete year of metered gas where available. The value is user-entered and weather and occupancy can change.')
    if history is not None:
        estimate = history_prediction if history_prediction is not None else predict_history(history, p)
        if not estimate['available']:
            return dict(kind='history_persistence', estimate_kwh=history['readings']['2023'],
                        interval_kwh=None, reference_year=2024,
                        limitation='Source-2023 gas carried forward to source-2024. The fitted artifact is unavailable.')
        kind = 'compatible_history_model'
    else:
        estimate = property_prediction if property_prediction is not None else predict(p)
        kind = 'property_model_context'
    if not estimate['available']:
        return dict(kind='unknown', estimate_kwh=None, interval_kwh=None, limitation=estimate['reason'])
    return dict(kind=kind, estimate_kwh=estimate['prediction_kwh'],
                interval_kwh=[estimate['lower_kwh'], estimate['upper_kwh']],
                observed_holdout_coverage=estimate['interval_test_coverage'], reference_year=estimate['reference_year'],
                calibration_warning=estimate.get('calibration_warning'),
                limitation=estimate['limitation'])


def physics_check(inputs=None):
    """Fixed-condition delivered fuel calculation for a surveyed fabric scenario."""
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict) or set(inputs) - set(PHYSICS_FIELDS):
        raise ValueError('Unknown retrofit physics fields')
    missing = []
    for field in PHYSICS_FIELDS:
        value = inputs.get(field)
        if value is None:
            missing.append(field)
            continue
        if field == 'survey_source':
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
                raise ValueError('Provide a survey or measurement reference (1–200 characters)')
        elif (type(value) not in (int, float) or not 0 < value <=
              (1 if field.startswith('efficiency_') else 10000)):
            raise ValueError('Invalid physics input: ' + field)
    result = dict(status='unknown' if missing else 'conditional_survey_scenario',
                  annual_space_heat_fuel_change_kwh=None, missing_inputs=missing, method_source_url=PHYSICS_SOURCE,
                  limitations=['Same heating degree days, balance temperature, heated area and use before and after.',
                               'Steady-state space heating only. Hot water, gains, intermittent heating, comfort take-back and ventilation changes require separate assessment.',
                               'Survey inputs are user supplied. This calculation has no calibrated household error bounds and is separate from ranking.'])
    if not missing:
        scale = inputs['heating_degree_days_k_days'] * 24 / 1000
        before = scale * inputs['htc_before_w_per_k'] / inputs['efficiency_before']
        after = scale * inputs['htc_after_w_per_k'] / inputs['efficiency_after']
        if not all(map(math.isfinite, (before, after))):
            raise ValueError('Non-finite space heating scenario')
        result.update(annual_space_heat_fuel_change_kwh=round(before - after, 1),
                      inputs=dict(inputs))
    return result


def survey_checks(payload):
    """Accept independent technical inputs, keyed by supported fabric measure."""
    if not isinstance(payload, dict) or set(payload) - FABRIC:
        raise ValueError('Retrofit physics must be keyed by a supported fabric measure ID')
    return {measure_id: physics_check(value) for measure_id, value in payload.items()}


def decision_impact(measures, p, scenario, hazard, *, eligibility_reason=None, survey=None):
    """Publish the existing energy scenario alongside a versioned evidence record."""
    ids = [m['id'] for m in measures if m.get('category') == 'Energy']
    scope_reason = 'Outside pilot; no regional transfer established.' if hazard.get('coverage') == 'outside' else None
    reason = eligibility_reason or scope_reason
    if reason:
        result = dict(available=False, central_kwh=None, objective_kwh=None, unquantified=[], reason=reason)
    else:
        result = savings(measures, p, scenario)
    applicable = result.get('applicability', {})
    supported = result['available']
    source_ids = applicable.get('evidence_ids', [])
    registry = evidence()['registry']
    if not supported and not reason and len(ids) == 1 and ids[0] in FABRIC:
        candidate = evidence()['groups'][NAMES[ids[0]]]['property_type'].get(group_for(p))
        if candidate and not candidate['available']:
            source_ids = [candidate['evidence_id']]
    sources = [dict(id=key, url=registry[key]['source_url'], locator=registry[key]['locator'],
                    period=registry[key].get('period'),
                    population=registry[key].get('population', applicable.get('source_population'))) for key in source_ids]
    missing = []
    if not supported and not scope_reason:
        if p.need_age == 'unknown' and p.age == 'post-1980' and FABRIC.intersection(ids):
            missing.append('pre_2000_construction_confirmation')
        if {'wall', 'cavity'}.intersection(ids) and p.wall_type == 'unknown':
            missing.append('wall_construction_and_existing_insulation')
    result['retrofit_effect'] = dict(
        version=VERSION, measure_id=ids[0] if len(ids) == 1 else None, measure_ids=ids,
        eligible=bool(ids) and not eligibility_reason,
        eligibility_status='ineligible' if eligibility_reason else 'conditional' if ids else 'not_applicable',
        effect_type='published_group_scenario' if supported else 'unknown',
        effect_estimate=result['central_kwh'], effect_unit='kWh_gas_per_year',
        evidence_level=('published_adjusted_partial_match' if applicable.get('classification') == 'partially_transferable'
                        else 'published_adjusted_marginal_match') if supported else 'insufficient_applicable_evidence',
        reference_group=result.get('group'), sample_size=result.get('n'),
        published_group_median_kwh=result.get('published_group_median_kwh'),
        baseline=dict(kwh=result['baseline_kwh'], origin=result['baseline_origin']) if supported else None,
        uncertainty=dict(kind='transferred_group_interquartile_dispersion',
                         lower_kwh=result['lower_kwh'], upper_kwh=result['upper_kwh'],
                         interpretation=result['uncertainty']) if supported else None,
        source_ids=source_ids, sources=sources, missing_inputs=missing,
        limitations=[result['limitations'], *applicable['limitations']] if supported else [result['reason']],
        unquantified_components=result['unquantified'],
        professional_survey_required=bool(ids))
    if len(ids) == 1 and ids[0] in FABRIC and not reason and p.heating == 'gas':
        result['retrofit_effect']['physics_check'] = (survey or {}).get(ids[0]) or physics_check()
    return result
