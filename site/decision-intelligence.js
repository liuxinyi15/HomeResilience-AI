'use strict';

const evidenceLabels = {
 observed:'Observed or directly recorded', published_modelled:'Published modelled',
 engineering_assumption:'Engineering assumption', illustrative:'Illustrative', unavailable:'Unavailable',
 planning_preference:'Planning preference', independent_certification:'Independent certification',
 official_guidance:'Official guidance', published_guidance:'Published guidance',
 manufacturer_specification:'Manufacturer specification', market_price:'Market price at retrieval'
};
const evidenceLabel = value => evidenceLabels[value] || 'Unknown';

function plannerRecommendation(){
 const s=state.result.budget_decisions?.strategies.find(s=>s.key==='recommended_balance');
 if(!s)return '';
 return `<section class="panel"><h2>Recommended for your priorities · ${money(s.cost)}</h2><p>Priority · ${priorityName()} · weights for flood / energy / comfort: ${state.result.weights.join(' / ')}.</p>
 <p>${esc(s.explanation.why)}</p><p>${measureNames(s.ids)} · ${money(s.remaining_gbp)} unallocated.</p>
 <a href="#comparison" class="btn secondary">Compare budget strategies and select an action plan →</a></section>`;
}

function outcomeChange(d){
 if(!d)return '';
 return `<p><strong>Published group gas scenario change</strong> ${signed(d.energy_kwh,'kWh/year')} ·
 <strong>Conditional pathways added</strong> ${esc(d.pathways_gained.join(', ')||'None')} ·
 <strong>Pathways dropped</strong> ${esc(d.pathways_lost.join(', ')||'None')} ·
 <strong>Direct gas carbon scenario change</strong> ${signed(d.carbon_kg,'kgCO₂e/year')}</p>`;
}
function measureDifferenceTable(rows){
 if(!rows?.length)return '<p>No interventions in either plan.</p>';
 return `<div class="table-scroll"><table class="decision-table"><thead><tr><th>Measure</th><th>Change</th><th>Before</th><th>After</th><th>Difference</th></tr></thead><tbody>${rows.map(row=>
  `<tr><th>${esc(row.name)}</th><td>${esc(row.status.replaceAll('_',' '))}</td>
   <td>${row.before_gbp===null?'—':money(row.before_gbp)}${row.before_product?`<br><small>${esc(row.before_product)}</small>`:''}${row.before_material?`<br><small>${esc(row.before_material)}</small>`:''}</td>
   <td>${row.after_gbp===null?'—':money(row.after_gbp)}${row.after_product?`<br><small>${esc(row.after_product)}</small>`:''}${row.after_material?`<br><small>${esc(row.after_material)}</small>`:''}</td>
   <td>${signed(row.delta_gbp,'£')}</td></tr>`).join('')}</tbody></table></div>`;
}
function decisionBudgetPanel(){
 const d=state.result.budget_decisions;
 if(!d)return '';
 const key=d.upgrades[lab.upgradeKey]?lab.upgradeKey:d.strategies[0].key;
 return `<section class="panel" id="budget-decisions"><h2>Plans for your budget</h2>
 <div class="decision-budget"><label>Available budget <strong id="lab-budget-display">${money(state.budget)}</strong>
 <input id="lab-budget-range" type="range" min="0" max="100000" step="1" value="${state.budget}"></label>
 <form id="lab-budget-form"><label>Exact budget (£)<input id="lab-budget-number" type="number" min="0" max="100000" step="0.01" required value="${state.budget}"></label>
 <button class="btn secondary small" type="submit">Apply budget</button></form></div>
 <p class="note">Use Enter, Apply budget or leave the field to update. Edited plans are kept and rechecked.</p>
 <p>${esc(d.risk_explanation)}</p><div class="lab-summary">${d.strategies.map(strategyCard).join('')}</div>
 ${d.alternatives_note?`<p>${esc(d.alternatives_note)}</p>`:''}
 <section class="callout"><h3>Plan improvements in stages</h3>
 <label>Starting plan<select id="upgrade-start">${d.strategies.map(s=>`<option value="${s.key}" ${s.key===key?'selected':''}>${esc(strategyName(s.name))}</option>`).join('')}</select></label>
 ${upgradeCard(d.upgrades[key], key)}</section>
 <p class="note">Quality comparison needs more evidence. Review exact product specifications and maintenance terms in the Lab.</p><details><summary>Quality, maintenance and lifecycle cost</summary><p>${esc(d.quality_note)}</p><p>${esc(d.lifecycle_note)}</p></details></section>`;
}
function strategyCard(s,index){
 const e=s.explanation,d=e.extra_budget;
 return `<article class="strategy budget-strategy"><h3>${esc(strategyName(s.name))}</h3><div class="big-cost">${money(s.cost)}</div>
 <p>${esc(e.why)}</p>
 <p><strong>Work included</strong> ${s.ids.length?measureNames(s.ids):'Free preparedness only'}</p>
 <p>${s.pathways.covered.length?`<strong>Conditional flood coverage</strong> ${esc(s.pathways.covered.join(', '))}.`:'No additional flood pathways addressed.'}
 ${s.gas_savings.available?`<strong>Published group gas scenario</strong> ${kwh(s.gas_savings.central_kwh)}/year.`:'Gas effect unknown.'}</p>
 <p class="note">${money(s.remaining_gbp)} unallocated. Higher allowance ${money(s.costs.high)} ${s.high_cost_feasible?'fits your budget':'exceeds your budget'}.</p>
 ${d?`<p><strong>Compared with the ${money(e.cheaper_alternative.cost)} option</strong> ${esc(e.why_not_cheaper)}</p>`:''}
 <button class="btn secondary" data-recommended-action="${index}">Use this plan for action →</button>
 <details><summary>When would the cheaper plan be enough?</summary><p>${esc(e.when_another_is_better)}</p>
 ${d?`<p>${measureNames(e.cheaper_alternative.ids)}. Allowance difference ${signed(d.extra_gbp,'£')}.</p>${outcomeChange(d)}${measureDifferenceTable(d.measures)}`:''}</details>
 <details><summary>What should I verify?</summary>
 <ul>${e.professional_verification.map(c=>`<li><strong>${measureNames([c.id])}</strong> ${esc(c.requirement)}</li>`).join('')}
 ${e.uncertainties.map(text=>`<li>${esc(text)}</li>`).join('')}</ul></details>
 <details><summary>Planning assumptions</summary><p>${money(s.costs.low)}–${money(s.costs.high)} allowance range. ${s.stability.feasible_cases}/9 tested assumptions fit your budget.
 Preference points ${s.utility.toFixed(1)}. ${esc(state.result.budget_decisions.method[s.key])} ${esc(s.stability.interpretation)}</p></details></article>`;
}
function upgradeStep(u,label){
 if(!u)return '';
 return `<p><strong>${label}</strong> · ${money(u.cost)} total (${signed(u.delta.extra_gbp,'£')} against the starting plan).
 Higher allowance ${money(u.cost_high)} ${u.high_cost_feasible?'fits':'exceeds'} this budget.</p>
 <p>Add ${measureNames(u.added)}. Keep ${measureNames(u.retained)}.
 ${u.removed.length?`Remove ${measureNames(u.removed)}.`:''}
 ${u.new_dependencies.length?`New prerequisites ${measureNames(u.new_dependencies)}.`:''} ${u.retained_dependencies.length?`Reused prerequisites ${measureNames(u.retained_dependencies)}.`:''}</p>${outcomeChange(u.delta)}`;
}
function upgradeCard(path,key){
 return `${path.spending_note?`<p>${esc(path.spending_note)}</p>`:''}
 ${[['next_add_only','First opportunity to add work'],['next_replacement','First opportunity to replace work']].map(([id,label])=>{
  const u=path[id];
  return u?`<details><summary>${label} · ${money(u.budget_required)} budget</summary>${upgradeStep(u,label)}
   <p class="note">${money(u.extra_budget_gbp)} additional budget. ${esc(u.phase_cost_note)}</p>
   ${lab.managed||lab.plans.length<4?`<button class="btn secondary small" data-upgrade="${id}" data-strategy-key="${key}">Compare at this budget →</button>`:''}</details>`:'';
 }).join('')}
 ${path.scenarios.map(s=>`<details><summary>${money(s.budget)} budget (${signed(s.budget-state.budget,'£')})</summary>
 ${upgradeStep(s.add_only,'Keep existing work and add')}${upgradeStep(s.reoptimised,'Replacement option')}
 <p>${esc(s.reason)}</p></details>`).join('')}
 <p class="note">Each allowance is for the whole plan. Ask for a phased quote covering repeat visits, removal and making good.</p>`;
}

function qualityCost(cost){
 if(!cost)return 'Unknown';
 const value=cost.low_gbp===cost.high_gbp?money(cost.low_gbp):money(cost.low_gbp)+'–'+money(cost.high_gbp);
 const included=v=>v===null?'Unknown':v?'included':'excluded';
 return `${value} · ${esc(cost.scope)} · Installation ${included(cost.installation_included)} · VAT ${included(cost.vat_included)} · ${evidenceLabel(cost.evidence_class)}`;
}
function qualityTable(records){
 const cells=(label,render)=>`<tr><th>${label}</th>${records.map(q=>`<td>${render(q)}</td>`).join('')}</tr>`;
 const field=(label,key)=>cells(label,q=>esc(q[key]??'Unknown'));
 return `<div class="table-scroll"><table class="decision-table"><thead><tr><th>Evidence field</th>${records.map(q=>`<th>${esc(q.name)}</th>`).join('')}</tr></thead><tbody>
 ${field('Manufacturer','manufacturer')}${field('Specification','specification')}
 ${cells('Certification & test scope',q=>q.certification?esc(`${q.certification.standard} · ${q.certification.certificate} · ${q.certification.scope.replaceAll('_',' ')} · DMWD ${q.certification.dmwd_m} m`):'Unknown')}
 ${field('Material','material')}${field('Installation requirements','installation_requirements')}
 ${cells('Indicative price',q=>qualityCost(q.indicative_cost))}${field('Maintenance','maintenance')}
 ${field('Installed product price','installation_cost')}${field('Maintenance cost','maintenance_cost')}${field('Replacement requirements','replacement_requirements')}${field('Warranty','warranty')}${field('Expected lifetime','expected_lifetime')}
 ${field('Evidence limits','limitations')}
 ${cells('Source & retrieval',q=>q.sources.length?q.sources.map(s=>`<p><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(strategyName(s.name))} ↗</a><br><small>${evidenceLabel(s.kind)} · ${esc(s.retrieved??'Retrieval date unknown')}</small></p>`).join(''):'Unknown')}
 </tbody></table></div>`;
}
function qualityComparisons(){
 const products=lab.evidence?.products||[];
 return `<section class="panel"><h3>Product and installation quality</h3><p class="note">Compare only listed configurations for the same measure. A catalogue price is a separate line of evidence from the plan’s installation cost. Confirm aperture fit, scope, service costs and warranty in the quote.</p>
 ${state.catalogue.map(m=>{
  const options=products.filter(r=>r.application==='domestic_opening'&&r.measure_ids.includes(m.id)&&r.quality);
  return options.length?`<details><summary>${esc(m.name)} · ${options.length} documented configuration${options.length>1?'s':''}</summary>${qualityTable(options.map(r=>r.quality))}</details>`:'';
 }).join('')}</section>`;
}
function lifecycleInputs(plan){
 const fields=[['years','Horizon (years)',1,50,1],['annual_maintenance_gbp','Whole-plan maintenance per year (£)',0,1000000,.01],
 ['replacements_gbp','One replacement event (£)',0,1000000,.01],['replacement_year','Replacement year, if applicable',1,50,1],
 ['discount_rate_pct','Annual discount rate (%)',0,100,.01]];
 return `<details data-lifecycle-details ${lab.open['lifecycle:'+lab.plans.indexOf(plan)]?'open':''}><summary>Optional lifecycle cost scenario</summary>
 <p class="note">Enter your assumptions in today’s pounds. Leave unknown inputs blank and enter zero only for a confirmed zero cost.</p>
 <label><input type="checkbox" data-lifecycle-field="complete_installed_scope" ${plan.lifecycle?.complete_installed_scope?'checked':''}>
 My upfront allowances cover every selected measure, including installation and VAT.</label>
 <div class="lab-quotes">${fields.map(([k,label,min,max,step])=>`<label>${label}<input type="number" data-lifecycle-field="${k}" min="${min}" max="${max}" step="${step}" value="${plan.lifecycle?.[k]??''}"></label>`).join('')}</div></details>`;
}
function lifecycleDisplay(plan){
 const life=plan.lifecycle;
 if(!life)return '';
 if(!life.totals_gbp)return '<p class="note">Lifecycle cost cannot yet be compared reliably.</p>';
 const value=s=>money(life.sensitivity[s].totals_gbp[plan.cost_scenario]);
 return `<p class="note"><strong>Illustrative lifecycle expenditure</strong> ${money(life.totals_gbp[plan.cost_scenario])} over ${life.inputs.years} years at ${life.inputs.discount_rate_pct}%.
 Discount-rate sensitivity ${value('higher_rate')}–${value('lower_rate')}.</p>`;
}
function applyBudget(value){
 const budget=Number(value);
 if(budget===state.budget)return;
 state.budget=budget;
 state.plan=0;
 compute();
}
function bindBudgetControls(prefix){
 const range=$('#'+prefix+'budget-range'),amount=$('#'+prefix+'budget-number'),form=$('#'+prefix+'budget-form');
 if(!amount)return;
 const apply=()=>{if(amount.reportValidity())applyBudget(amount.value);};
 let clickingSubmit=false;
 form.onpointerdown=e=>{
  clickingSubmit=!!e.target.closest('button[type="submit"]');
 };
 form.onsubmit=e=>{e.preventDefault();clickingSubmit=false;apply();};
 amount.onblur=()=>{
  if(!clickingSubmit)apply();
  clickingSubmit=false;
 };
 range.oninput=()=>{amount.value=range.value;};
 range.onchange=()=>applyBudget(range.value);
}
function bindDecisionBudget(){
 bindBudgetControls('lab-');
 $('#upgrade-start').onchange=e=>{lab.upgradeKey=e.target.value;render();$('#upgrade-start').focus();};
 document.querySelectorAll('[data-recommended-action]').forEach(b=>b.onclick=()=>{
  state.plan=+b.dataset.recommendedAction;lab.active=null;chooseJourney(pack(),'action');
 });
 document.querySelectorAll('[data-upgrade]').forEach(b=>b.onclick=async()=>{
  const upgrade=state.result.budget_decisions.upgrades[b.dataset.strategyKey][b.dataset.upgrade];
  const from=state.result.budget_decisions.strategies.find(s=>s.key===b.dataset.strategyKey);
  const fromDraft=cloneLabPlan(from,from.name+' · starting plan');
  const useCleanComparison=lab.managed;
  state.budget=upgrade.budget_required;
  state.plan=0;
  await compute(false);
  if(state.pending||state.invalidDraft||state.page!=='comparison'||state.budget!==upgrade.budget_required)return;
  if(useCleanComparison){
   lab.plans=[];lab.originals=[];lab.baseline=0;lab.active=null;lab.open={};
   addLabPlan(fromDraft);
  }
  const start=lab.plans.findIndex(p=>JSON.stringify(p.ids)===JSON.stringify(fromDraft.ids)
   && JSON.stringify(p.cost_overrides)===JSON.stringify(fromDraft.cost_overrides)
   && !Object.keys(p.products).length && !Object.keys(p.materials).length);
  if(start>=0)lab.baseline=start;
  else if(lab.plans.length<=2){lab.baseline=lab.plans.length;addLabPlan(fromDraft);}
  addLabPlan(cloneLabPlan(upgrade,upgrade.kind==='add_only'?'Phased upgrade':'Replacement option'));
  lab.managed=false;
  render();
 });
}

function actionMarkdown(p){
 const md=value=>esc(value??'Unknown').replace(/\s+/g,' ').replaceAll('|','\\|');
 const actual=p.custom?p:null;
 const profile=state.result.property;
 const budgetStrategy=state.result.budget_decisions?.strategies.find(s=>
  s.name===p.name && s.cost===p.cost && s.ids.length===p.ids.length && s.ids.every(id=>p.ids.includes(id)));
 const savings=p.gas_savings;
 const covered=p.pathways?.covered||p.benefit_ledger?.flood_planning?.covered||[];
 const energy=savings.available
  ? `${kwh(savings.central_kwh)}/year gas scenario. Group ${md(savings.group)}, n=${savings.n}. Base ${kwh(savings.baseline_kwh)}. Group dispersion ${kwh(savings.lower_kwh)}–${kwh(savings.upper_kwh)}. [Official NEED source](${savings.source_url}).`
  : `Unknown. ${md(savings.reason)}`;
 const measureLine=m=>{
  const q=m.quality_evidence;
  return [`- **${md(m.name)}** · ${money(m['cost_'+state.scenario])}. ${md(m.cost_origin)}.`,
   `  - Verify ${md(q?.installation_requirements||m.flood_evidence?.record.prerequisites||m.limitations||m.rationale)}`,
   m.requires.length?`  - Prerequisites ${measureNames(m.requires)}.`:'',
   m.material_note?`  - Quotation scope ${md(m.material_note)}.`:'',
   m.product?`  - Selected configuration ${md(m.product.record.name)}. [Certification](${m.product.record.source_url}).`:'',
   q?.maintenance?`  - Maintenance ${md(q.maintenance)}`:'',
   q?.warranty?`  - Warranty ${md(q.warranty)}`:'',
   `  - [Measure source](${m.source_url}).`].filter(Boolean).join('\n');
 };
 const stage=category=>p.measures.filter(m=>(m.category==='Survey')===category).map(measureLine).join('\n')||'None selected.';
 const difference=actual?.difference;
 const lifecycle=p.lifecycle?.totals_gbp
  ? `${money(p.lifecycle.totals_gbp[state.scenario])} over ${p.lifecycle.inputs.years} years at ${p.lifecycle.inputs.discount_rate_pct}%, illustrative expenditure under entered assumptions.`
  : 'Unknown. Confirm servicing, maintenance and replacement costs.';
 return `# HomeResilience AI — Your action plan

## Selected strategy: ${md(strategyName(p.name))}

${md(state.result.assessment.input_origin)}. ${md(profile.property_type)}, ${profile.area} m², ${md(profile.age)}, EPC ${md(profile.epc)}, ${md(profile.heating)} heating. Mapped area exposure ${md(state.result.assessment.exposure.category)}.

Available budget **${money(state.budget)}**. Selected ${md(state.scenario)} cost **${money(p.cost)}**. Allowance range ${money(p.cost_low)}–${money(p.cost_high)}. Unallocated **${money(p.remaining)}**.
${budgetStrategy?`\n${budgetStrategy.explanation.why}\n\n${budgetStrategy.explanation.when_another_is_better}\n`:''}
## Expected outcomes and uncertainty

- Gas · ${energy}
- Conditional flood pathways addressed · ${md(covered.join(', ')||'None')}. Household loss reduction is unknown.
- Lifecycle expenditure · ${lifecycle}

## First · Prepare and verify

Check [official flood information](https://www.gov.uk/check-long-term-flood-risk) and the applicable warnings. Confirm design depth, openings, drainage, fabric moisture, ventilation and permissions.

${stage(true)}

## Then · Get scoped quotes and install suitable work

Confirm VAT, installation, compatibility, repeated visits and making good. Keep unallocated funds available for scope changes.

${stage(false)}

## After installation · Maintain and review

Retain survey and commissioning records. Ask each supplier for a written service schedule and confirm how warranty terms depend on maintenance.

## Custom specifications and comparison

${difference?`Baseline difference ${signed(difference.cost,'£')}.\n\n${difference.explanations.map(text=>'- '+text).join('\n')}`:'No edited alternative selected.'}

The companion evidence JSON contains the full calculations, assumptions and source registry.
`;
}
