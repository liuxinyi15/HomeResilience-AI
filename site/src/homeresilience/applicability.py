"""Documented cohort matching and survey requirements; no confidence percentages."""
from .impacts import effect_for

def assess(measures,p):
 effect,reason=effect_for(measures,p)
 ids={m['id'] for m in measures};requirements=[];limitations=[];exclusions=[]
 if not ids & {'loft','wall','cavity'}:exclusions.append('No matching published gas-insulation intervention definition.')
 if p.property_type=='flat':exclusions.append('Flats are excluded from the source impact population.')
 if p.heating!='gas':exclusions.append('Source gas impacts cannot quantify this heating fuel or heat-pump outcome.')
 if p.need_age=='4':exclusions.append('Insulation source population excludes construction from 2000 onwards.')
 if p.need_age=='unknown' and p.age=='post-1980':exclusions.append('Construction before 2000 has not been established. Confirm the source-compatible construction band before quantifying insulation effects.')
 if 'loft'in ids and not p.loft_uninsulated:exclusions.append('No uninsulated private loft reported.')
 for key,wall in [('wall','solid'),('cavity','cavity')]:
  if key in ids and (p.wall_type!=wall or p.listed):exclusions.append('An eligible uninsulated '+wall+' wall and appropriate permissions have not been established.')
 if effect is None or exclusions:
  return dict(classification='unsupported',label='Insufficient applicable evidence to quantify savings.',cohort_match='Not established',quantifiable=False,reason=' '.join(exclusions) or reason,requirements=[],limitations=['Unknown effect is not zero benefit.'],source_sample_n=effect['n'] if effect else None,evidence_ids=[effect['evidence_id']] if effect else [])
 requirements.append('Professional retrofit assessment: fabric condition, ventilation, moisture, installation scope and permissions.')
 partial=[]
 if 'loft'in ids and ('wall'in ids or 'cavity'in ids):partial.append('Combined cohort has no property-type subgroup; do not combine separate marginal effects.')
 if p.property_type=='terraced' and p.terrace_position=='unknown':partial.append('Terrace subtype unknown: only the broader non-flat cohort is used.')
 limitations.extend(['Published weighted matched-control difference-in-differences; residual confounding and scheme selection remain.','Reported household quartiles are dispersion, not confidence or personal prediction intervals.','Pre-installation consumption, smart-meter transitions, private works and occupancy are not verified.','Age, EPC and region marginal groups are not crossed with the property-type estimate.'])
 return dict(classification='partially_transferable' if partial else 'requires_professional_survey',label='Partially transferable published evidence' if partial else 'Published group match; professional survey required',
  cohort_match='Partial marginal/combined population match' if partial else 'Direct match to the published property-type group only; not a direct individual causal estimate',quantifiable=True,reason=effect['selection'],requirements=requirements+partial,limitations=limitations,source_population='England/Wales non-flat pre-2000 gas-insulation intervention cohorts with valid matched readings; government-scheme records',source_sample_n=effect['n'],group=effect['group'],matching_method='Published adjusted observational matched-control estimator',source_evidence='Directly applicable published group statistic; transfer to an individual remains unvalidated',evidence_ids=[effect['evidence_id']])
