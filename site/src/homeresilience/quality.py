"""Source-scoped product/measure quality and optional lifecycle arithmetic."""
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIFECYCLE_FIELDS = ('years', 'annual_maintenance_gbp', 'replacements_gbp',
                    'replacement_year', 'discount_rate_pct', 'complete_installed_scope')
MANUFACTURERS = {'bsi-m3': 'M3 Global Flood Technologies Limited',
                 'bsi-kingsley': 'Kingsley Plastics Limited'}


@lru_cache(maxsize=1)
def quality_source():
    return json.loads((ROOT / 'data/processed/quality-evidence-v1.json').read_text())


def quality_record(measure, product=None):
    data = quality_source()
    if product is None:
        facts = data['measure_details'].get(measure['id'], {})
        flood = measure.get('flood_evidence') or {}
        sources = [dict(name=r['id'], url=r['url'], retrieved=None, kind='official_guidance') for r in flood.get('source_references', [])]
        spec = measure['description']
        certification = None
        material = None
        prerequisites = flood.get('record', {}).get('prerequisites')
        maintenance = flood.get('maintenance')
    else:
        facts = data['product_details'].get(product['id'], {})
        if 'copy_from' in facts:
            facts = data['product_details'][facts['copy_from']]
        sources = [dict(name='BSI directory', url=product['source_url'], retrieved=product['checked'], kind='independent_certification')]
        spec = product['dimensions']
        certification = dict(standard=product['standard'], certificate=product['certificate'],
                             scope=product['application'], dmwd_m=product['dmwd_m'], evidence_class='independent_certification')
        material = product['material'] if not product['material'].startswith('Not specified') else None
        prerequisites = 'Verify exact configuration and surveyed aperture with the installer.'
        maintenance = None
    for key in facts.get('source_ids', []):
        kind = ('market_price' if key == 'm3-airbrick-listing' else
                'manufacturer_specification' if key.startswith('m3-') else 'official_guidance' if key == 'clean-energy-insulation' else 'published_guidance')
        sources.append(dict(data['sources'][key], kind=kind))
    result = dict(name=(product or measure)['name'], specification=facts.get('specification', spec),
                certification=certification, material=facts.get('material', material),
                installation_requirements=facts.get('installation_requirements', prerequisites),
                indicative_cost=facts.get('indicative_cost'), maintenance=facts.get('maintenance', maintenance),
                maintenance_cost=None, warranty=facts.get('warranty'),
                expected_lifetime=facts.get('expected_lifetime'), sources=sources,
                limitations=facts.get('limitations', (product or {}).get('limitations',
                            'Property-specific specification, installer terms and costs depend on survey and quotation.')))

    price = result['indicative_cost']
    primary = sources[0] if sources else {}
    dimensions = dict(
        product_id=data['configuration_models'].get((product or {}).get('id')), configuration_id=(product or {}).get('id'),
        manufacturer=MANUFACTURERS.get((product or {}).get('source_id')),
        product_name=product['name'] if product else None,
        intervention_type=product['measure_ids'] if product else [measure['id']],
        technical_specification=(product or {}).get('dimensions') or result['specification'],
        certification_scheme='BSI Kitemark' if certification else None,
        certificate_reference=(certification or {}).get('certificate'),
        verified_performance_conditions=dict(configuration=product['name'], dimensions=product['dimensions'],
                                             dmwd_m=product['dmwd_m'],
                                             application=product['application']) if certification else None,
        installation_requirements=result['installation_requirements'],
        maintenance_requirements=result['maintenance'],
        warranty_terms=result['warranty'], service_life_evidence=result['expected_lifetime'],
        replacement_requirements=None, product_price=price if price and price['installation_included'] is False else None,
        installation_cost=None, VAT=price['vat_included'] if price else None,
        quote_scope=price['scope'] if price else None,
        source_url=primary.get('url') or (measure or {}).get('source_url'), source_date=primary.get('retrieved'),
        evidence_quality=dict(certification='independent_certification' if certification else 'unknown',
                              maintenance='manufacturer_specification' if product and result['maintenance']
                              else 'official_guidance' if result['maintenance'] else 'unknown',
                              warranty='manufacturer_statement' if result['warranty'] else 'unknown',
                              service_life='manufacturer_expectation' if result['expected_lifetime'] else 'unknown',
                              durability_comparison='insufficient_comparable_evidence'),
        verification_status='listed_configuration_recheck_before_installation' if certification
                            else 'generic_scope_survey_required')
    result.update(dimensions)
    result['unknown_fields'] = sorted(k for k, v in dimensions.items() if v is None)
    return result


def lifecycle_cost(inputs, upfront):
    """Discounted whole-installed-plan scenario with explicit scope and timing."""
    if not isinstance(inputs, dict) or set(inputs) - set(LIFECYCLE_FIELDS):
        raise ValueError('Unknown lifecycle fields')
    years = inputs.get('years')
    replacement = inputs.get('replacements_gbp')
    when = inputs.get('replacement_year')
    rate = inputs.get('discount_rate_pct')
    scope = inputs.get('complete_installed_scope')
    if years is not None and (type(years) is not int or not 1 <= years <= 50):
        raise ValueError('Lifecycle horizon must be 1–50 whole years')
    if when is not None and (type(when) is not int or not 1 <= when <= 50):
        raise ValueError('Replacement year must be between 1 and 50')
    if rate is not None and (type(rate) not in (int, float) or not 0 <= rate <= 100):
        raise ValueError('Annual discount rate must be between 0% and 100%')
    if scope is not None and type(scope) is not bool:
        raise ValueError('Installed scope confirmation must be true or false')
    for field in ('annual_maintenance_gbp', 'replacements_gbp'):
        value = inputs.get(field)
        if value is not None and (type(value) not in (int, float) or not 0 <= value <= 1000000):
            raise ValueError('Lifecycle costs must be finite and between £0 and £1,000,000')
    missing = [field for field in LIFECYCLE_FIELDS
               if inputs.get(field) is None and (field != 'replacement_year' or replacement)]
    if scope is False:
        missing.append('complete_installed_scope')
    if replacement and when is not None and years is not None and when > years:
        raise ValueError('Replacement year must fall within the analysis horizon')

    def scenario(rate_pct):
        factor = 1 + rate_pct / 100
        maintenance = sum(inputs['annual_maintenance_gbp'] / factor ** year for year in range(1, years + 1))
        replacement_cost = replacement / factor ** when if replacement else 0
        return dict(discount_rate_pct=rate_pct, maintenance_pv_gbp=round(maintenance, 2),
                    replacement_pv_gbp=round(replacement_cost, 2),
                    totals_gbp={key: round(value + maintenance + replacement_cost, 2)
                                for key, value in upfront.items()})

    scenarios = ({'lower_rate': scenario(round(max(0, rate - 2), 4)), 'selected_rate': scenario(rate),
                  'higher_rate': scenario(round(min(100, rate + 2), 4))} if not missing else None)
    return dict(totals_gbp=scenarios['selected_rate']['totals_gbp'] if scenarios else None,
                inputs=dict(inputs), missing_inputs=missing, sensitivity=scenarios,
                evidence_class='illustrative' if scenarios else 'unavailable',
                limitation=('Illustrative whole-plan expenditure with a user-confirmed installed scope including VAT. '
                            'Maintenance occurs at each year-end. A single entered replacement event is discounted '
                            'at its stated year. Fuel costs, inflation, residual value and avoided flood losses are excluded.'))
