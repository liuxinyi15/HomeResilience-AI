'use strict';

const home = () => Journey.current();
const journeyToday = () => new Date().toLocaleDateString('sv-SE');
const locationKey = () => JSON.stringify([state.lon,state.lat]);
const riskContext = () => {
 const {annual_gas_kwh,...property}=effectiveProperty();
 return JSON.stringify([property,locationKey(),state.provenance?.retrieved_at]);
};
const journeyContext = () => JSON.stringify([riskContext(), state.budget, state.priority, state.scenario,
 state.benefitScenario, state.costOverrides, state.profile.annual_gas_kwh, state.historyInput]);
const riskCurrent = () => !!state.result && !state.invalidDraft && home().assessment?.signature===riskContext();
const analysisCurrent = () => !!state.result && !state.pending && !state.invalidDraft && state.resultContext===journeyContext();
const activeSelection = () => Journey.selected(home(),analysisCurrent()?journeyContext():null);
function checkQuoteValidity() {
 const h=home(), ids=h.selection?.quoteIds || [];
 if (!h.selection?.outdated && ids.some(id=>!h.quotes.some(q=>q.id===id && q.validUntil>=journeyToday()))) {
  Journey.invalidate(h,null,'A supporting quote expired or was removed.');
  saveJourney();
  updateJourneyStatus();
 }
}
const activeFunding = () => Journey.dependent(home().funding,activeSelection());
const activeScope = () => activeFunding() && Journey.dependent(home().scope,activeSelection()) && home().scope.fundingKey===activeFunding().key ? home().scope : null;
const deliverySelection = activeSelection;
const workNeedsReassessment = () => !!state.result && !riskCurrent();
const strategyName = name => typeof name==='string' ? name.replace(/^Recommended Balance(?=$| copy\b| · starting plan$)/,'Recommended for your priorities') : name;
const priorityName = () => ({balanced:'Balanced',flood:'Flood resilience',energy:'Energy efficiency'})[state.priority];
const journeyText = value => esc(value || 'Unknown');
const stageTitles = {property:'Understand', planner:'Plan', comparison:'Compare', funding:'Fund',
 action:'Deliver', verify:'Verify', passport:'Passport', maintenance:'Maintain'};
function saveJourney() {
 if (!Journey.persist(window.localStorage)) error(Error('Browser storage is unavailable. This journey will last for this session.'));
}
function appliedJourney() {
 const {profile_origin, energy_history} = labContext();
 Journey.session.inputsByHome[Journey.session.home] = {
  profile:state.profile,profileOrigin:profile_origin,budget:state.budget,priority:state.priority,scenario:state.scenario,
  lon:state.lon,lat:state.lat,benefitScenario:state.benefitScenario,costOverrides:state.costOverrides,
  floodLayer:state.floodLayer,historyInput:energy_history
 };
 const h = home(), previous=h.assessment, sourceDate=state.provenance?.retrieved_at;
 if (previous && JSON.stringify(previous.property)!==JSON.stringify(state.result.property)) {
  if (previous.property.heating!==state.result.property.heating) addTrigger('heating');
  if (previous.property.epc!==state.result.property.epc) addTrigger('epc');
  if (!h.triggers.some(trigger=>!trigger.applied)) addTrigger('profile');
 }
 if (previous?.sourceDate && previous.sourceDate!==sourceDate) addTrigger('flood');
 const signature = riskContext();
 Journey.invalidate(h, journeyContext());
 if (signature !== h.assessment?.signature || h.triggers.some(trigger=>!trigger.applied)) h.assessment = {
  signature, date:new Date().toISOString(), exposure:state.result.assessment.exposure,
  limitations:state.result.assessment.uncertainty, property:state.result.property,
  source:'Environment Agency · York pilot', sourceDate, profileOrigin:profile_origin
 };
 h.triggers = h.triggers.map(trigger => trigger.applied ? trigger : {...trigger, applied:journeyToday()});
 saveJourney();
}
function effectiveProperty() {
 return {...state.profile, completed_measures:Journey.reportedCompleted(home(),locationKey())};
}
function chooseJourney(plan, destination='quotes') {
 const context = journeyContext();
 const key = JSON.stringify([context, plan.name, plan.cost, plan.ids, plan.measures.map(m => [m.product?.record.id, m.cost_low, m.cost_base, m.cost_high, m.material_note, m.product?.reported_aperture_depth_m])]);
 const h=home();
 if (!analysisCurrent()) return;
 if (h.selection?.key!==key || h.selection.outdated) {
  Journey.archive(h);
  const quoteIds=plan.measures.map(m=>m.material_note?.match(/^Quote record (.+)$/)?.[1]).filter(Boolean);
  h.selection = {key, context, plan, quoteIds, date:journeyToday()};
  h.funding=null;
  h.scope=null;
 }
 saveJourney();
 updateJourneyStatus();
 location.hash = destination;
 render();
}
function journeyProgress() {
 const h=home();
 checkQuoteValidity();
 const status = Journey.status(h, analysisCurrent()?journeyContext():null, riskCurrent(), journeyToday());
 const current=state.page==='quotes'?'comparison':state.page;
 const mobileStages={overview:'Start',property:stageTitles.property,planner:stageTitles.planner,
  comparison:stageTitles.comparison,quotes:'Products & quotes',funding:stageTitles.funding,action:stageTitles.action,
  verify:stageTitles.verify,passport:stageTitles.passport,maintenance:stageTitles.maintenance,explorer:'Climate explorer',evidence:'Evidence & models'};
 const mobile=`<label class="journey-mobile">Journey stage<select id="mobile-stage">${Object.entries(mobileStages).map(([route,title])=>
  `<option value="${route}" ${state.page===route?'selected':''}>${title}${status[route]?' · '+status[route]:''}</option>`).join('')}</select></label>`;
 const desktop=state.page === 'overview' || state.page === 'evidence' ? '' :
  '<ol class="journey-progress" aria-label="Journey progress">' + Object.entries(stageTitles).map(([route, title]) =>
   `<li><a href="#${route}" ${current === route ? 'aria-current="step"' : ''}>${title}<small>${status[route]}</small></a></li>`).join('') + '</ol>';
 $('#journey-progress').innerHTML=mobile+desktop;
 const control=$('#mobile-stage');
 if (control) control.onchange=()=>{location.hash=control.value;};
}
function journeyStart() {
 return head('YOUR RESILIENCE JOURNEY','A clearer way to improve your home','Understand what your home needs, choose work you can afford and keep a record for the years ahead.') +
 `<section class="hero"><div class="hero-text"><h2>From climate risk to practical action</h2><p>Explore property risks, suitable improvements and indicative costs. Compare scoped quotes, plan how to fund the work and keep installation and maintenance records.</p><button id="start-own-home" class="btn lime">Start with my home →</button></div>${skyline()}</section>
 <div class="equal-col"><section class="panel"><h2>What to expect</h2><p>Insurance quotes and lending approvals come from providers. Savings and future flood losses are uncertain. A qualified surveyor confirms what is suitable for your property.</p></section>
 <section class="panel"><h2>Your data choices</h2><p>Use the sample profile or edit the fields you know. Saving keeps your home profile and Passport in this browser. On shared devices, leave saving off. Avoid entering bank details or sensitive document contents.</p>
 <label><input id="journey-consent" type="checkbox" ${Journey.session.save?'checked':''}> Save my journey on this browser</label></section></div>
 <section class="panel"><h2>Walk through Emma’s York home</h2><p>Fictional demonstration · family semi · £10,000 planning budget. The demo has a separate record from your own home.</p>
 <button class="btn" data-profile="family">Open Emma’s demo →</button>
 <button class="btn secondary" id="own-home">Open my home →</button> <button class="btn secondary" id="reset-emma">Reset Emma demo</button><div class="lab-toolbar" aria-label="Other sample homes">
 ${state.profiles.filter(p=>p.id!=='family').map(p=>`<button class="btn secondary" data-profile="${p.id}">${esc(p.name)} · ${money(p.budget)}</button>`).join(' ')}</div></section>`;
}
function problemMap() {
 const r=state.result, p=r.property, h=r.assessment.exposure;
 const pathways = {openings:'Doors and thresholds', vents:'Air bricks and ventilation', drainage:'Drain backflow', services:'Electrical services', floor_recovery:'Flooring and recovery'};
 const ledger=r.packages[0].benefit_ledger.flood_planning;
 return `<section class="panel"><h2>Your home’s problem map</h2><div class="journey-grid">
 <div><h3>What we know</h3><p>Mapped river and sea exposure is <strong>${esc(h.category)}</strong>. Environment Agency area evidence · ${journeyText(h.coverage)}.</p>
 <p>${journeyText(p.property_type)} · EPC ${journeyText(p.epc)} · ${journeyText(p.heating)} heating. ${esc(r.assessment.input_origin)}.</p>
 <p>Reported existing measures ${measureNames([...new Set([...p.existing_protection, ...(p.completed_measures || [])])])}.</p></div>
 <div><h3>What may matter</h3><p>Potential pathways to inspect include ${ledger.remaining_relevant.map(id=>pathways[id]).join(', ') || 'none identified from this profile'}.</p>
 <p>${p.loft_uninsulated?'Check the loft’s insulation and ventilation. ':''}${['cavity','solid','unknown'].includes(p.wall_type)?'Wall construction and condition may affect insulation options.':''}</p></div>
 <div><h3>What still needs checking</h3><p>Confirm aperture dimensions, property-level flood depth and compatibility on site. Confirm wall construction and moisture condition before insulation.</p>
 <p>Check surface water and other hazards through official services.</p><a href="#explorer">Explore the official map →</a></div></div></section>`;
}
function outdatedNotice() {
 return '<div class="callout amber" data-outdated><strong>Previous decisions are outdated.</strong> Review the latest inputs and confirm a current portfolio. Earlier decisions are kept in Passport history.</div>';
}
function updateJourneyStatus() {
 syncStatus(state.result && !analysisCurrent()?'Outdated — reassessment required.':
  home().selection?.outdated?'Inputs reassessed. Previous decisions are outdated. Confirm a current portfolio.':'');
}
function assessmentRequired() {
 return '<section class="panel"><h2>Refresh your plan after completed work</h2><p>The Passport has new records. Reassess your home to use them in suitability checks and budget recommendations.</p><a class="btn" href="#passport">Reassess from your Passport →</a></section>';
}
function candidatePlan() {
 return `<section class="panel"><h2>Which measures could suit your home?</h2><p>These checks use the current property profile. Open a measure to see what a professional needs to confirm.</p>
 <div class="candidate-grid">${state.result.candidates.map(m=>`<details><summary>${esc(m.name)} <span class="badge grey">${esc(m.status)}</span></summary>
 <p>${esc(m.rationale)}</p><p>${esc(m.reason || m.description)}</p>
 <p><strong>Professional verification required</strong> ${journeyText(m.professional_check)}</p>
 <p>${esc(m.evidence_type)} · <a href="${esc(m.source_url)}" target="_blank" rel="noopener">Evidence source ↗</a></p>
 ${measureEvidence(m)}</details>`).join('')}</div></section>`;
}
function comparisonExecutive() {
 const {strategies, quality_note}=state.result.budget_decisions;
 const message=state.budget<=2000?'Start small without making the wrong first move.':state.budget>=25000?'Spend more only when the evidence supports better long-term value.':'Understand what the extra money buys.';
 return `<section class="panel"><h2>${message}</h2><p>Priority · ${priorityName()} · weights for flood / energy / comfort: ${state.result.weights.join(' / ')}.</p><div class="journey-grid">${strategies.map(s=>{
  const e=s.explanation, d=e.extra_budget;
  return `<article><h3>${esc(strategyName(s.name))}</h3><p><strong>${money(s.cost)}</strong> planning allowance</p>
  ${d?`<p>${money(d.extra_gbp)} more than the ${money(e.cheaper_alternative.cost)} alternative. ${esc(e.why_not_cheaper)}</p><p>${esc(e.when_another_is_better)}</p>`:`<p>${esc(e.why)}</p>`}
  <p>${money(s.remaining_gbp)} left in budget · ${money(s.costs.high)} higher allowance.</p>
  <button class="btn secondary" data-journey-select="${esc(s.key)}">Choose ${esc(strategyName(s.name))} →</button></article>`;
 }).join('')}</div>${state.budget>=25000?`<p>${esc(quality_note)}</p>`:''}</section>`;
}

const productsFor = measure => (lab.evidence?.products || []).filter(p=>p.application==='domestic_opening' && p.measure_ids.includes(measure));
const doorProducts = () => productsFor('flood-door');
const configurationName = id => lab.evidence?.products.find(p=>p.id===id)?.name || id;
const scopeValue = value => ({included:'Included',excluded:'Excluded'})[value] || 'Unknown';
const quoteOrigin = {user:'User-entered quotation', contractor:'Contractor quotation · user transcribed', demo:'Synthetic demo quotation'};
function demoQuotes() {
 const [first, second] = doorProducts();
 return [
  {name:'Demo quote A', total:3100, origin:'demo', configuration:first.id, validUntil:'2027-01-31',
   scope:{product:'included',installation:'included',vat:'included',survey:'included',removal:'included',adaptation:'excluded',maintenance:'excluded',warranty:'included'}},
  {name:'Demo quote B', total:2350, origin:'demo', configuration:second.id, validUntil:'2027-01-31',
   scope:{product:'included',installation:'included',vat:'unknown',survey:'unknown',removal:'excluded',adaptation:'unknown',maintenance:'unknown',warranty:'unknown'}}
 ];
}
function quoteComparisons(quotes, keys, configuration) {
 if (quotes.length < 2) return '<p>Enter at least two quotes to compare scope.</p>';
 const [base, ...others] = quotes;
 return `<p class="note">Each quote is compared with ${esc(base.name)}.</p>` + others.map(q => {
  const d=Journey.compareQuotes(base,q,journeyToday(),{keys,configuration});
  const price=d.delta===0?'has the same stated total':`appears ${money(Math.abs(d.delta))} ${d.delta<0?'cheaper':'more expensive'}`;
  return `<div class="callout ${d.comparable?'':'amber'}"><strong>${esc(q.name)} ${price}.</strong>
  ${d.comparable?'Reported scope matches. Confirm the same quantities, site conditions and terms before accepting.':'These quotes are not yet directly comparable.'}
  ${d.gaps.length?`Check ${esc(d.gaps.join(', '))}.`:''} ${d.different.length?`Different scope or specification includes ${esc(d.different.join(', '))}.`:''}
  ${base.origin!==q.origin?'The source types also differ.':''}</div>`;
 }).join('');
}
function quoteApplies(quote, selection) {
 return !!selection && (quote.selection===selection.key ||
  (quote.id && quote.context===selection.context && selection.plan.measures.some(m=>m.material_note==='Quote record '+quote.id)));
}
function quoteCanDraft(quote) {
 const essential=state.catalogue.find(m=>m.id===quote.measure)?.category==='Survey'?['survey','vat']:['product','installation','vat','survey'];
 return quote.id && quote.total<=100000 && quote.validUntil && quote.validUntil>=journeyToday() &&
  essential.every(k=>quote.scope[k]==='included') &&
  (!productsFor(quote.measure).length || productsFor(quote.measure).some(p=>p.id===quote.configuration));
}
function quoteDraft(selection, name) {
 const plan=selection.plan, draft=cloneLabPlan(plan,name);
 for (const m of plan.measures) {
  if (m.product) draft.products[m.id]=m.product.record.id;
  if (m.material_note) draft.materials[m.id]=m.material_note;
  if (m.product?.reported_aperture_depth_m!=null) draft.depths[m.id]=m.product.reported_aperture_depth_m;
  if (m.cost_origin?.startsWith('User')) draft.cost_overrides[m.id]={low:m.cost_low,base:m.cost_base,high:m.cost_high};
 }
 return draft;
}
function openQuoteDraft(draft, measure) {
 if (!lab.plans.length) loadBudgetPlans();
 if (lab.plans.length>=4) return false;
 invalidateLab();
 addLabPlan(draft);
 lab.managed=false;
 lab.open[(lab.plans.length-1)+':'+measure]=true;
 location.hash='comparison';
 return true;
}
function quotesPage() {
 const selection=activeSelection(), plan=selection?.plan;
 if (!selection) return head('03 / PRODUCT & QUOTE','Products for your selected plan','Confirm a current portfolio before comparing quotes.')+(home().selection?outdatedNotice():'')+next('comparison','Choose a current plan');
 const ids=plan.ids, measure=ids.includes(state.quoteMeasure)?state.quoteMeasure:ids.includes('flood-door')?'flood-door':ids[0];
 const door=measure==='flood-door', products=productsFor(measure), quotes=home().quotes.filter(q=>quoteApplies(q,selection) && q.measure===measure);
 const survey=state.catalogue.find(m=>m.id===measure)?.category==='Survey';
 const fields=Object.entries(Journey.scopeFields).filter(([key])=>!survey || ['survey','vat'].includes(key));
 const alternatives=doorProducts().length && !ids.includes('flood-door');
 const candidate=state.result.candidates.find(m=>m.id==='flood-door');
 const canDraft=lab.plans.length<4;
 const doorTable=`<h3>Certified flood door configurations</h3><p>Independent certification covers the listed configuration and test conditions. Confirm aperture fit, threshold depth and installed scope with your installer.</p>${doorProducts().length?qualityTable(doorProducts().map(p=>p.quality)):'<p>Configuration evidence is unavailable.</p>'}`;
 const configForm=`<form id="journey-configuration" class="form-grid"><label>Shortlist a configuration<select name="configuration">${doorProducts().map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></label><div><button class="btn secondary" ${canDraft?'':'disabled'}>Check configuration in the Lab →</button></div></form>`;
 return head('03 / PRODUCT & QUOTE','Compare what is actually included','Review products and quotations for the measures in your current plan.')+
 `<section class="panel" id="plan-products"><h2>Products for your selected plan</h2><p>${esc(strategyName(plan.name))} · ${measureNames(ids)}</p>
 ${measure?`<label>Measure to compare<select id="quote-measure">${ids.map(id=>`<option value="${id}" ${id===measure?'selected':''}>${measureNames([id])}</option>`).join('')}</select></label>
 ${door?doorTable:products.length?`<h3>Certified configurations · ${measureNames([measure])}</h3>${qualityTable(products.map(p=>p.quality))}`:'<p>Verified product catalogue evidence is unavailable for this measure. Compare what the contractor includes and ask for the relevant specification or survey deliverables.</p>'}`:'<p>This plan has no paid measures to quote.</p>'}</section>
 ${alternatives?`<section class="panel"><details><summary>Explore alternatives</summary><p>These options are outside your selected plan. Adding or replacing a measure may change your costs and funding. The Comparison Lab checks the revised plan before you can confirm it.</p><p>Flood doors are not included in this plan. ${state.result.excluded.some(m=>m.id==='flood-door')?'Not applicable under the current inputs. '+esc(candidate?.reason || ''):ids.includes('survey')?'Relevant alternative.':'Requires a flood survey.'}</p>
 ${doorTable}${state.result.excluded.some(m=>m.id==='flood-door')?'':configForm}</details></section>`:''}
 ${measure?` <section class="panel"><h2>Compare quotes side by side</h2><p>Quote totals and scope are reported separately from certification and planning allowances. A scoped, in-date quote can be checked as a Lab draft. Confirm the draft as a new portfolio before using its costs for funding.</p>
 ${quoteComparisons(quotes,fields.map(([key])=>key),!survey)}
 ${quotes.length?`<div class="table-scroll"><table><thead><tr><th scope="col">Scope</th>${quotes.map((q,i)=>`<th scope="col">${esc(q.name)}<br><button class="btn secondary small" data-remove-quote="${home().quotes.indexOf(q)}" aria-label="Remove ${esc(q.name)}">Remove</button>${quoteCanDraft(q)?`<button class="btn secondary small" data-quote-draft="${home().quotes.indexOf(q)}" ${canDraft?'':'disabled'}>Check quote in Lab →</button>`:''}</th>`).join('')}</tr></thead><tbody>
 ${[['Stated total',q=>money(q.total)],['Source type',q=>quoteOrigin[q.origin]],['Reported configuration',q=>journeyText(configurationName(q.configuration))],['Valid until',q=>journeyText(q.validUntil)],...fields.map(([key,label])=>[label,q=>scopeValue(q.scope[key])])].map(([label,value])=>`<tr><th scope="row">${label}</th>${quotes.map(q=>`<td>${value(q)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:''}
 ${door && Journey.session.home==='family' && doorProducts().length>=2?'<button class="btn secondary" id="demo-quotes">Load two fictional Emma quotes</button>':''}
 ${door && doorProducts().length?configForm:''}
 <form id="journey-quote" class="form-grid"><label>Quote label<input name="name" required maxlength="80"></label>
 <label>Stated total (£)<input name="total" type="number" required min="0" max="1000000" step=".01"></label>
 <label>Source<select name="origin"><option value="user">User-entered quotation</option><option value="contractor">Contractor quotation · user transcribed</option></select></label>
 ${products.length?`<label>Listed configuration on quote<select name="configuration"><option value="">Unknown or outside listed configurations</option>${products.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></label>`:''}
 <label>Quote valid until<input name="validUntil" type="date"></label>
 ${fields.map(([key,label])=>`<label>${label}<select name="${key}"><option value="unknown">Unknown</option><option value="included">Included</option><option value="excluded">Excluded</option></select></label>`).join('')}
 <div><button class="btn secondary" ${quotes.length>=8?'disabled':''}>Save quote</button></div></form></section>`:''}`+next('funding','Explore funding pathways');
}

const fundingRoutes = {none:'Funding not required',self:'Self-funded', staged:'Staged retrofit', incentive:'Explore an incentive', finance:'Finance-assisted illustration'};
const fundingProgramme = {
 programme:'Warm Homes: Local Grant', provider:'Local councils in England', measures:['loft','wall','cavity','heat-pump'],
 geography:'England', conditions:'Private homes with EPC D–G, subject to household or area criteria, survey and council funding.',
 benefitType:'Council-arranged eligible improvements', benefitValue:null, source:'https://www.gov.uk/apply-warm-homes-local-grant',
 lastVerified:'2026-11-09', status:'Potentially relevant'
};
function fundingSettings(selection) {
 const funding=activeFunding();
 return funding ? funding : {route:'staged', upfront:Math.min(2000,selection.plan.cost), contribution:0, months:60, rate:0};
}
function fundingMilestones(selection, upfront) {
 return Journey.stages(selection.plan.measures, upfront, state.scenario, state.result.property.completed_measures);
}
function phaseList(phases) {
 return `<ol>${phases.map((phase,i)=>`<li><strong>Stage ${i+1} · ${i?'Add-only':'Start'} · ${money(phase.cost)} cumulative allowance</strong><br>${phase.added.length?measureNames(phase.added):'Free preparedness only at this upfront amount.'}</li>`).join('')}</ol>`;
}
function fundingPage() {
 const selection=activeSelection();
 const title=head('04 / FUND','Find a way to pay for the work','See how much you need upfront and what you could do in stages.');
 if (!selection) return title+(home().selection?outdatedNotice():'')+next('comparison','Choose a current plan');
 const plan=selection.plan, settings=fundingSettings(selection);
 const programme=fundingProgramme, relevant=state.result.assessment.exposure.coverage!=='outside' && plan.ids.some(id=>programme.measures.includes(id)) && ['D','E','F','G','unknown'].includes(state.result.property.epc);
 const pay=Journey.finance(plan.cost, settings.contribution, settings.months, settings.rate);
 const upgrade=state.result.budget_decisions.upgrades[plan.key];
 return title+`<section class="panel"><h2>${esc(strategyName(plan.name))}</h2><p>${money(plan.cost)} planning allowance · higher allowance ${money(plan.cost_high)}.</p>
 <div class="journey-grid"><article><h3>Self-funded</h3><p>Set aside ${money(plan.cost)} upfront at the selected allowance.</p></article>
 <article><h3>Staged retrofit</h3>${phaseList(fundingMilestones(selection,settings.upfront))}
 <p>These planning allowances describe the whole scope through each stage. Repeat visits, removal and making good can increase the real cost. Ask for a phased quotation.</p></article>
 <article><h3>Potential incentives</h3>${relevant?`<p><strong>${programme.status}</strong> · ${programme.programme}. ${programme.conditions}</p>
 <p>${programme.benefitType}. Project contribution ${journeyText(programme.benefitValue)}. Checked ${programme.lastVerified}.</p><a href="${programme.source}" target="_blank" rel="noopener">Check with the official service ↗</a>`:'<p>Unknown for this scope. Check current local support with the relevant provider.</p>'}</article></div>
 <h3>Finance-assisted example</h3><p><strong>Illustrative only</strong> · no lending decision or personalised financial advice.</p>
 <p>${money(pay.principal)} financed over ${settings.months} months at a user-set fixed nominal annual rate of ${settings.rate}%, with monthly compounding and zero fees. Estimated ${money(pay.monthly)} per month and ${money(pay.total)} total repayments.</p>
 <form id="journey-funding" class="form-grid"><label>Funding route<select name="route">${Object.entries(fundingRoutes).map(([id,name])=>`<option value="${id}" ${settings.route===id?'selected':''}>${name}</option>`).join('')}</select></label>
 <label>Spend available now (£)<input name="upfront" type="number" min="0" max="100000" step=".01" required value="${settings.upfront}"></label>
 <label>Illustrative cash contribution (£)<input name="contribution" type="number" min="0" max="${plan.cost}" step=".01" required value="${settings.contribution}"></label>
 <label>Illustrative term (months)<input name="months" type="number" min="1" max="360" required value="${settings.months}"></label>
 <label>Illustrative nominal annual interest (%)<input name="rate" type="number" min="0" max="100" step=".01" required value="${settings.rate}"></label>
 <div><button class="btn">Calculate and save pathway</button></div></form>
 ${upgrade?`<details><summary>Options beyond this portfolio</summary>${[['next_add_only','Add-only upgrade'],['next_replacement','Replacement or re-optimisation']].map(([key,label])=>upgradeStep(upgrade[key],label)).join('') || esc(upgrade.spending_note || 'No distinct upgrade is available under current assumptions.')}</details>`:''}</section>`+next('action','Prepare your project scope');
}
function providerRequirements(m) {
 return {
  professionalScope:m.category==='Survey'?m.description:m.flood_evidence?.record?.prerequisites || m.quality_evidence?.installation_requirements || m.description,
  registration:null,
  productAuthorisation:m.product?'Ask the manufacturer whether approved installation is required for this configuration.':null,
  geographicCoverage:null,
  documentation:m.category==='Survey'?['Survey report']:['Invoice','Completion record',...(m.product?['Configuration certificate']:[])]
 };
}
function scopeMeasure(m) {
 const check=m.flood_evidence?.record?.prerequisites || m.quality_evidence?.installation_requirements || 'Confirm site conditions and required documentation with the professional.';
 const product=m.product?.record, provider=providerRequirements(m);
 return `<article class="measure"><h3>${esc(m.name)}</h3><p>${esc(m.description)}</p>
 <p><strong>Prerequisites</strong> ${measureNames(m.requires)}. ${esc(check)}</p>
 <p><strong>Configuration and certificate</strong> ${product?`${esc(product.name)} · ${esc(product.certificate)}. Confirm current certificate scope and aperture fit.`:'Professional verification required.'}</p>
 <p><strong>Quote scope</strong> ${m.id==='flood-door'?'<a href="#quotes">Review saved flood-door quotes →</a> ':''}Itemise survey, labour, supply, VAT, disposal and any adaptations. Specify what will be documented at handover.</p>
 <details><summary>What the provider needs to demonstrate</summary>
 <p><strong>Professional scope</strong> ${esc(provider.professionalScope)}</p>
 <p><strong>Required registration</strong> ${journeyText(provider.registration)} · Confirm the applicable trade requirements and ask for comparable work references.</p>
 <p><strong>Product authorisation</strong> ${journeyText(provider.productAuthorisation)}</p>
 <p><strong>Provider coverage</strong> ${journeyText(provider.geographicCoverage)} · Confirm availability in your area.</p>
 <p><strong>Handover documents</strong> ${esc(provider.documentation.join(', '))}.</p></details>
 <a href="${esc(product?.source_url || m.source_url)}" target="_blank" rel="noopener">Source ↗</a></article>`;
}
function projectScope() {
 const selection=deliverySelection();
 if (!selection) return (home().selection?outdatedNotice():'')+`<section class="panel"><h2>Project scope</h2><p>Choose a current portfolio to build a scope. Your previous records remain in the Passport.</p><a class="btn secondary" href="#comparison">Choose a plan →</a></section>`;
 const {plan}=selection, funding=activeFunding();
 if (!funding) return next('funding','Confirm funding before delivery');
 const staged=funding?.selection===selection.key && funding.route==='staged';
 const phases=staged?funding.phases:[{ids:plan.ids,added:plan.ids,cost:plan.cost}];
 return `<section class="panel"><h2>Project scope · ${esc(strategyName(plan.name))}</h2><p>Use this scope when asking for quotes and checking installer suitability.</p>
 ${!activeSelection()?'<p>This is the recorded project. Its allowances reflect the original planning inputs.</p>':''}
 ${staged?phaseList(phases):''}
 ${plan.measures.map(scopeMeasure).join('')}
 <div class="lab-toolbar">${phases.map((phase,i)=>`<button class="btn" data-journey-scope="${i}" ${phase.ids.length?'':'disabled'}>${staged?`Record work through Stage ${i+1}`:'Record planned work'} →</button>`).join('')}</div></section>`;
}

const evidenceTypes={completion:'Completion record',invoice:'Invoice',certificate:'Certificate',report:'Survey report',warranty:'Warranty',photo:'Photograph',commissioning:'Commissioning record'};
function recordHeading(id, record) {
 return `${measureNames([id])} <span class="badge grey">${esc(Journey.recordStatus(record))}</span>`;
}
function verificationCard(id, record) {
 const installation=record.installation || {};
 const gaps=Journey.verificationGaps(record);
 return `<article class="measure"><h3>${recordHeading(id,record)}</h3>
 <p>Planned configuration ${journeyText(record.configuration)}. ${record.category==='Survey'?'Record the professional’s completion date and survey report.':'Record the installed configuration, date and provider.'}</p>
 ${record.installation?'':`<form class="form-grid" data-progress-measure="${id}"><label>Before work starts<select name="progress">${['Planned','Quoted','Scheduled'].map(s=>`<option ${record.progress===s?'selected':''}>${s}</option>`).join('')}</select></label><div><button class="btn secondary small">Save progress</button></div></form>`}
 <details ${record.installation?'':'open'}><summary>${record.installation?'Edit completed work':'Record completed work'}</summary>
 <form class="form-grid" data-install-measure="${id}">
 <label>${record.category==='Survey'?'Survey date':'Installation date'}<input name="date" type="date" max="${journeyToday()}" required value="${esc(installation.date || '')}"></label>
 <label>Installer or surveyor<input name="provider" required maxlength="100" value="${esc(installation.provider || '')}"></label>
 <label>Product name<input name="product" maxlength="100" value="${esc(installation.product || '')}"></label>
 <label>Configuration / model<input name="configuration" maxlength="120" value="${esc(installation.configuration || '')}" ${record.configuration?'required':''}></label>
 <label>Warranty reference<input name="warranty" maxlength="120" value="${esc(installation.warranty || '')}"></label>
 <label>Warranty expiry<input name="warrantyExpiry" type="date" value="${esc(installation.warrantyExpiry || '')}"></label>
 <div><button class="btn secondary">Save completion details</button></div></form></details>
 ${record.installation?`<p>Recorded ${journeyText(installation.date)} · ${journeyText(installation.provider)} · ${journeyText(installation.configuration)}.</p>
 <ul>${record.evidence.map(item=>`<li>${esc(evidenceTypes[item.type])} · ${esc(item.reference)} ${item.file?`· ${esc(item.file.name)}`:''} · ${esc(item.origin)}</li>`).join('')}</ul>
 <form class="form-grid" data-evidence-measure="${id}">
 <label>Evidence type<select name="type">${Object.entries(evidenceTypes).map(([type,label])=>`<option value="${type}">${label}</option>`).join('')}</select></label>
 <label>Document reference or short description<input name="reference" required maxlength="150"></label>
 <label>Optional file (metadata only)<input name="file" type="file"></label>
 <div><button class="btn secondary">Add evidence</button></div></form>
 <p>${gaps.length?`Evidence still required ${esc(gaps.map(type=>evidenceTypes[type] || type).join(', '))}.`:'Required document references supplied. Review the actual records before confirming.'}</p>
 <form data-review-measure="${id}"><label><input name="review" type="checkbox" required> I reviewed the documents against the delivered scope and confirmed any configuration differences.</label> <button class="btn">Record verification review</button></form>`:''}</article>`;
}
function verifyPage() {
 return head('06 / VERIFY','Plan vs installed','Record what was delivered and check the documents that support it.')+
 `<section class="panel"><h2>Work in your Passport</h2>${Journey.session.home==='family'?'<p class="callout">Fictional demo workspace. Use sample document references and dates.</p>':''}<p>Verified means you declared that you checked the required documents against the scope. The app records references and optional file metadata. A qualified professional checks the installation itself.</p>
 ${Object.entries(home().records).filter(([id,r])=>r.installation || activeScope()?.ids.includes(id)).map(([id,r])=>verificationCard(id,r)).join('') || '<p>No work recorded. Record a project scope to begin.</p>'}
 ${home().records && Object.keys(home().records).length?next('passport','Open your Passport'):next('action','Prepare a project scope')}</section>`;
}

function maintenanceCard(id, record) {
 const m=record.maintenance || {}, status=Journey.maintenanceStatus(record,journeyToday());
 return `<article class="measure"><h3>${measureNames([id])} <span class="badge grey">${esc(status)}</span></h3>
 <p>${m.source?`Schedule source ${esc(m.source)} · Next due ${journeyText(m.due)}.`:'Follow manufacturer or installer maintenance schedule. No verified interval currently stored.'}</p>
 ${m.professional?'<p>Professional service required.</p>':''}
 ${m.completed?`<p>Last completion ${esc(m.completed.date)} · ${journeyText(m.completed.provider)} · ${journeyText(m.completed.document)}. ${esc(m.completed.note)}</p>`:''}
 <details><summary>Record a documented schedule</summary>
 <form class="form-grid" data-maintenance-measure="${id}">
 <label>Manufacturer or installer document<input name="source" required maxlength="150" value="${esc(m.source || '')}"></label>
 <label>Documented next due date<input type="date" name="due" value="${esc(m.due || '')}"></label>
 <label><input type="checkbox" name="professional" ${m.professional?'checked':''}> Professional service required</label>
 <label><input type="checkbox" name="confirmed" required> I checked the schedule in this document</label>
 <div><button class="btn secondary">Save documented schedule</button></div></form></details>
 ${m.source?`<details><summary>Record maintenance completed</summary>
 <form class="form-grid" data-service-measure="${id}">
 <label>Completed on<input type="date" name="date" required max="${journeyToday()}"></label>
 <label>Provider<input name="provider" maxlength="100"></label><label>Document reference<input name="document" maxlength="120"></label>
 <label>Note<input name="note" maxlength="150"></label>
 <label>Next documented due date, if given<input type="date" name="due"></label>
 <div><button class="btn secondary">Save maintenance record</button></div></form></details>`:''}</article>`;
}
function maintenancePage() {
 const installed=Object.entries(home().records).filter(([,r])=>r.installation && r.category!=='Survey');
 return head('07 / MAINTAIN','Keep your improvements working','Use the schedule supplied for the installed configuration and keep service records together.')+
 `<section class="panel"><h2>Maintenance schedule</h2>${Journey.session.home==='family'?'<p class="callout">Fictional demo schedules illustrate the workflow.</p>':''}${installed.map(([id,r])=>maintenanceCard(id,r)).join('') || '<p>Installed measures will appear here after you record completed work.</p>'}</section>`+
 reassessPanel()+next('passport','Return to your Passport');
}
const reassessReasons={flood:'Flood dataset changed',heating:'Heating changed',installation:'Work recorded',warranty:'Warranty expired',
 maintenance:'Maintenance overdue',epc:'EPC changed',climate:'Climate data changed',profile:'Property details updated',manual:'Homeowner requested reassessment'};
function reassessPanel() {
 const h=home(), today=journeyToday();
 const reminders=Object.entries(h.records).flatMap(([id,r])=>[
  ...(Journey.maintenanceStatus(r,today)==='Overdue'?[measureNames([id])+' maintenance overdue']:[]),
  ...(r.installation?.warrantyExpiry && r.installation.warrantyExpiry<=today?[measureNames([id])+' warranty expiry reached']:[])
 ]);
 if (state.blankHome) return next('property','Enter your home details');
 return `<section class="panel"><h2>Reassess home</h2><p>Update any changed property details, then use the current profile and recorded completed work to recalculate suitability and recommendations.</p>
 <a href="#property">Update property details →</a>
 ${reminders.length?`<ul>${reminders.map(text=>`<li>${text}</li>`).join('')}</ul>`:''}
 ${h.triggers.length?`<details><summary>Reassessment history</summary><ul>${h.triggers.map(t=>`<li>${esc(reassessReasons[t.reason])} · ${esc(t.date)} · ${t.applied?'Applied '+esc(t.applied):'Reassessment pending'}</li>`).join('')}</ul></details>`:''}
 <form id="journey-reassess" class="form-grid"><label>Reason<select name="reason">${Object.entries(reassessReasons).map(([id,label])=>`<option value="${id}" ${id==='manual'?'selected':''}>${label}</option>`).join('')}</select></label><div><button class="btn">Reassess home →</button></div></form></section>`;
}
function historicalDecisions(h) {
 return [...(h.history || []), ...(!activeSelection() && h.selection ?
  [{selection:h.selection,funding:h.funding,scope:h.scope,reason:h.selection.outdated || 'Reassessment required.'}] : [])];
}
function decisionHistory(h) {
 const history=historicalDecisions(h);
 return history.length?`<section class="panel historical"><h2>Decision history</h2><p>Historical · outdated decisions kept for reference.</p>
 ${history.map(({selection,funding,scope,reason})=>`<article class="measure"><strong>${esc(strategyName(selection.plan.name))}</strong> · ${money(selection.plan.cost)} · ${journeyText(selection.date)}
 <p>${esc(reason)} ${funding?'Historical funding · '+esc(fundingRoutes[funding.route])+'.':''} ${scope?'Historical delivery scope.':''}</p></article>`).join('')}
 <a href="#comparison">Review current options →</a></section>`:'';
}
function passportPage() {
 const h=home(), a=h.assessment, p=state.profile || {};
 const records=Object.entries(h.records), installed=[
  ...records.filter(([,r])=>r.installation && r.category!=='Survey'),
  ...(h.pastRecords || []).filter(({record})=>record.category!=='Survey').map(({id,record})=>[id,record])
 ];
 const funding=activeFunding(), remaining=funding?.phases?.filter(phase=>phase.added.some(id=>!h.records[id]?.installation)) || [];
 const selected=activeSelection();
 return head('HOME RESILIENCE PASSPORT','Your home’s resilience record','See what you learned, what was installed and what needs attention next.')+
 `<div class="equal-col"><section class="panel"><h2>Property</h2><p>${journeyText(p.property_type)} · ${journeyText(p.age)} · ${p.area?esc(p.area)+' m²':'Floor area unknown'}.</p>
 <p>EPC ${journeyText(p.epc)} · ${journeyText(p.heating)} heating · wall construction ${journeyText(p.wall_type)}.</p><p>${a?.profileOrigin==='demo'?'Synthetic demonstration profile':'Homeowner-reported profile'}. <a href="#property">Update your home →</a></p></section>
 <section class="panel"><h2>Latest risk assessment</h2><p>${a?(riskCurrent()?'Current':'Outdated · reassessment required'):'No assessment'}</p><p>${journeyText(a?.exposure.category)} mapped river and sea exposure · ${journeyText(a?.source)}.</p>
 <p>Assessed ${journeyText(a?.date?.slice(0,10))} · evidence retrieved ${journeyText(a?.sourceDate?.slice(0,10))} · coverage ${journeyText(a?.exposure.coverage)}.</p><p>${esc(a?.limitations.join(' ') || '')}</p></section></div>
 <section class="panel"><h2>Installed measures</h2>${installed.map(([id,r])=>`<article class="measure"><h3>${recordHeading(id,r)}</h3>
 <p>${journeyText(r.installation.product)} · configuration ${journeyText(r.installation.configuration)} · ${journeyText(r.installation.date)} · ${journeyText(r.installation.provider)}.</p>
 <p>Certificate ${journeyText(r.evidence.filter(e=>e.type==='certificate').map(e=>e.reference).join(', '))} · Warranty ${journeyText(r.installation.warranty)} · expires ${journeyText(r.installation.warrantyExpiry)}.</p>
 ${r.location && r.location!==locationKey()?'<p>Historical installation · recorded at the previous assessment location.</p>':''}<p>Maintenance · ${Journey.maintenanceStatus(r,journeyToday())}. <a href="#maintenance">View schedule →</a></p></article>`).join('') || '<p>Completed installations will appear here when recorded.</p>'}</section>
 <section class="panel"><h2>Funding and staging</h2><p>${funding?esc(fundingRoutes[funding.route]):'No current funding pathway'}. ${selected?`Last selected plan ${esc(strategyName(selected.plan.name))} · ${money(selected.plan.cost)} planning allowance.`:''}</p>
 ${funding?.phases?.length?phaseList(funding.phases):''}</section>
 ${decisionHistory(h)}
 <section class="panel"><h2>Evidence and next actions</h2>
 <p>${h.quotes.length} quote records · <a href="#quotes">View quote scope →</a></p>
 ${records.filter(([id,r])=>r.installation || activeScope()?.ids.includes(id)).map(([id,r])=>`<p><strong>${recordHeading(id,r)}</strong> · ${r.evidence.map(e=>`${esc(evidenceTypes[e.type])} ${esc(e.reference)}${e.file?' ('+esc(e.file.name)+')':''}`).join(', ') || 'Evidence pending'}.</p>`).join('')}
 ${remaining.length?`<p>Future staged work ${measureNames([...new Set(remaining.flatMap(phase=>phase.added).filter(id=>!h.records[id]?.installation))])}.</p>`:''}
 ${selected?.plan.ids.some(id=>!h.records[id]?.installation)?'<p>Check outstanding prerequisites and surveys in your project scope.</p>':''}
 <p><a href="#verify">Record documents or check verification →</a></p>
 <button class="btn secondary" id="passport-export">Export Passport JSON</button><p id="passport-export-status" role="status"></p></section>`+reassessPanel();
}

function addTrigger(reason) {
 const h=home();
 if (!h.triggers.some(t=>t.reason===reason && !t.applied)) h.triggers.push({reason,date:journeyToday()});
}
function bindJourney() {
 const bindForm=(selector, handler)=>document.querySelectorAll(selector).forEach(form=>form.onsubmit=e=>{
  e.preventDefault();
  if (handler(new FormData(form),form)===false) return;
  if (workNeedsReassessment()) {Journey.invalidate(home(),journeyContext());updateJourneyStatus();}
  saveJourney();
  render();
 });
 const consent=$('#journey-consent');
 if (consent) consent.onchange=()=>{Journey.session.save=consent.checked;saveJourney();};
 for (const id of ['own-home','start-own-home']) if ($('#'+id)) $('#'+id).onclick=()=>switchJourneyHome('home');
 if ($('#reset-emma')) $('#reset-emma').onclick=()=>{
  if (!window.confirm('Reset Emma’s fictional record, including quotes and completed work? My Home will be kept.')) return;
  delete Journey.session.homes.family;
  delete Journey.session.inputsByHome.family;
  saveJourney();
  switchJourneyHome('family');
 };
 document.querySelectorAll('[data-journey-select]').forEach(b=>b.onclick=()=>{lab.active=null;state.plan=state.result.packages.findIndex(p=>p.key===b.dataset.journeySelect);chooseJourney(pack());});
 if ($('#quote-measure')) $('#quote-measure').onchange=e=>{state.quoteMeasure=e.target.value;render();};
 if ($('#demo-quotes')) $('#demo-quotes').onclick=()=>{
  const selection=activeSelection();
  home().quotes=[...home().quotes.filter(q=>q.origin!=='demo' || q.selection!==selection.key),
   ...demoQuotes().map((q,i)=>({...q,id:'demo-door-'+i,context:selection.context,selection:selection.key,measure:'flood-door'}))];saveJourney();render();
 };
 document.querySelectorAll('[data-remove-quote]').forEach(b=>b.onclick=()=>{home().quotes.splice(+b.dataset.removeQuote,1);checkQuoteValidity();saveJourney();updateJourneyStatus();render();});
 bindForm('#journey-configuration', d=>{
  const selection=activeSelection();
  if (!selection || lab.plans.length>=4) return false;
  if (!lab.plans.length) loadBudgetPlans();
  if (lab.plans.length>=4) return false;
  const plan=selection.plan;
  const draft=quoteDraft(selection, 'Flood door configuration draft');
  if (!draft.ids.includes('flood-door')) {
   if (state.result.excluded.some(m=>m.id==='flood-door')) return false;
   const door=state.catalogue.find(m=>m.id==='flood-door');
   for (const id of door.excludes) removeLabMeasure(draft,id);
   draft.ids=[...new Set([...draft.ids,...door.requires.filter(id=>!state.result.property.completed_measures.includes(id)),'flood-door'])];
   draft.name=door.excludes.some(id=>plan.ids.includes(id))?'Flood door replacement draft':'Flood door addition draft';
  }
  draft.products['flood-door']=d.get('configuration');
  delete draft.depths['flood-door'];
  delete draft.materials['flood-door'];
  delete draft.cost_overrides['flood-door'];
  return openQuoteDraft(draft,'flood-door');
 });
 document.querySelectorAll('[data-quote-draft]').forEach(b=>b.onclick=()=>{
  const selection=activeSelection(), quote=home().quotes[+b.dataset.quoteDraft];
  if (!quote || !quoteApplies(quote,selection) || !quoteCanDraft(quote)) return;
  const draft=quoteDraft(selection,'Scoped quote draft');
  const id=quote.measure;
  if (quote.configuration) draft.products[id]=quote.configuration;
  if (draft.products[id]!==selection.plan.measures.find(m=>m.id===id)?.product?.record.id) delete draft.depths[id];
  draft.materials[id]='Quote record '+quote.id;
  draft.cost_overrides[id]={low:quote.total,base:quote.total,high:quote.total};
  if (openQuoteDraft(draft,id)) render();
 });
 bindForm('#journey-quote', d=>{
  const fields=Object.fromEntries(d);
  const selection=activeSelection(), measure=$('#quote-measure')?.value;
  if (!selection || !selection.plan.ids.includes(measure) || !fields.name.trim()) return false;
  home().quotes.push({id:crypto.randomUUID(),context:selection.context,selection:selection.key,measure,name:fields.name.trim(),total:Number(fields.total),origin:fields.origin,configuration:fields.configuration,validUntil:fields.validUntil,
   scope:Object.fromEntries(Object.keys(Journey.scopeFields).map(k=>[k,fields[k]]))});
 });
 bindForm('#journey-funding', d=>{
  const selection=activeSelection();
  if (!selection) return false;
  const upfront=Number(d.get('upfront'));
  const key=JSON.stringify([...d]);
  if (home().funding && home().funding.key!==key) {Journey.archive(home(),'Funding assumptions changed.');home().scope=null;}
  home().funding={key,selection:selection.key,planName:selection.plan.name,route:d.get('route'),upfront,contribution:Number(d.get('contribution')),
   months:Number(d.get('months')),rate:Number(d.get('rate')),phases:d.get('route')==='staged'?fundingMilestones(selection,upfront):[]};
 });
 document.querySelectorAll('[data-journey-scope]').forEach(b=>b.onclick=()=>{
  const selection=deliverySelection(), h=home();
  if (!selection) return;
  const funding=activeFunding();
  if (!funding) return;
  const staged=funding?.selection===selection.key && funding.route==='staged';
  const ids=staged?funding.phases[+b.dataset.journeyScope].ids:selection.plan.ids;
  const prior=activeScope()?.ids || [];
  h.scope={selection:selection.key,ids:[...new Set([...prior,...ids])],date:journeyToday(),fundingKey:funding.key,providers:Object.fromEntries(selection.plan.measures.map(m=>[m.id,providerRequirements(m)]))};
  selection.plan.measures.filter(m=>ids.includes(m.id)).forEach(m=>{
   const configuration=m.product?.record.name || '';
   if (h.records[m.id]?.installation && h.records[m.id].location && h.records[m.id].location!==locationKey()) {
    (h.pastRecords ||= []).push({id:m.id,record:h.records[m.id]});
    delete h.records[m.id];
   }
   const record=h.records[m.id] ||= {category:m.category,configuration,progress:'Planned',evidence:[],origin:Journey.session.home==='family'?'Fictional Emma demo':'User reported'};
   if (!record.installation) record.configuration=configuration;
  });
  saveJourney();
  location.hash='verify';
  render();
 });
 bindForm('[data-progress-measure]', (d,f)=>{home().records[f.dataset.progressMeasure].progress=d.get('progress');});
 bindForm('[data-install-measure]', (d,f)=>{
  const r=home().records[f.dataset.installMeasure];
  const details=Object.fromEntries([...d].map(([key,value])=>[key,value.trim()]));
  if (!details.provider || (r.configuration && !details.configuration)) return false;
  if (JSON.stringify(r.installation)===JSON.stringify(details)) return false;
  if (r.installation && ['date','provider','product','configuration'].some(key=>r.installation[key]!==details[key])) {
   r.archivedEvidence=[...(r.archivedEvidence || []),{installation:r.installation,evidence:r.evidence,verified:r.verified}];
   r.evidence=[];
   r.maintenance=null;
  }
  r.installation=details;
  r.location ||= locationKey();
  r.verified=null;
  r.reviewed=false;
  addTrigger('installation');
 });
 bindForm('[data-evidence-measure]', (d,f)=>{
  const r=home().records[f.dataset.evidenceMeasure], file=d.get('file'), reference=d.get('reference').trim();
  if (!reference) return false;
  r.evidence.push({type:d.get('type'),reference,origin:Journey.session.home==='family'?'Synthetic demo declaration':'User declared',file:file?.name?{name:file.name,size:file.size,type:file.type}:null});
 });
 bindForm('[data-review-measure]', (d,f)=>{
  const r=home().records[f.dataset.reviewMeasure];
  r.reviewed=true;
  r.verified=Journey.verificationGaps(r).length?null:{date:journeyToday(),origin:Journey.session.home==='family'?'Synthetic demo review':'User-attested document review'};
  if (r.verified && r.category==='Survey') addTrigger('installation');
 });
 bindForm('[data-maintenance-measure]', (d,f)=>{
  const r=home().records[f.dataset.maintenanceMeasure], source=d.get('source').trim();
  if (!source) return false;
  r.maintenance={...r.maintenance,source,due:d.get('due'),professional:d.has('professional'),confirmedOn:journeyToday()};
 });
 bindForm('[data-service-measure]', (d,f)=>{
  const r=home().records[f.dataset.serviceMeasure], {due,...completed}=Object.fromEntries(d);
  if (due && due<=completed.date) {
   const control=f.elements.due;
   control.setCustomValidity('The next due date must be after the completion date.');
   control.reportValidity();
   control.oninput=()=>control.setCustomValidity('');
   return false;
  }
  r.maintenance={...r.maintenance,due,completed,history:[...(r.maintenance.history || []),completed]};
 });
 if ($('#journey-reassess')) $('#journey-reassess').onsubmit=async e=>{
  e.preventDefault();
  if (state.blankHome || state.invalidDraft || state.pending) return;
  addTrigger(new FormData(e.currentTarget).get('reason'));
  state.plan=0;
  await compute(false);
  if (!state.invalidDraft && !state.pending) {location.hash='property';render();}
 };
 if ($('#passport-export')) $('#passport-export').onclick=()=>{
  const status=$('#passport-export-status');
  let href;
  try {
   href=URL.createObjectURL(new Blob([JSON.stringify(passportExport(),null,2)],{type:'application/json'}));
   const link=document.createElement('a');
   link.href=href;link.download='HomeResilience-passport.json';
   document.body.append(link);
   try {link.click();} finally {link.remove();}
   status.textContent='Passport exported. Check your downloads.';
  } catch (_) {
   status.textContent='Passport export failed. Please try again.';
  } finally {
   if (href) setTimeout(()=>URL.revokeObjectURL(href),1000);
  }
 };
}
function passportExport() {
 const h=home(), assessment=h.assessment;
 const decision=({selection,funding,scope,reason},status)=>({
  status,reason, strategy:strategyName(selection.plan.name), measures:selection.plan.ids,
  allowance:selection.plan.cost, selectedOn:selection.date,
  funding:funding?{route:funding.route,phases:funding.phases}:null,
  delivery:scope?{ids:scope.ids,date:scope.date}:null
 });
 const selection=activeSelection();
 const property=Object.fromEntries(['property_type','age','area','heating','epc','wall_type','existing_protection'].filter(k=>state.profile[k]!=null).map(k=>[k,state.profile[k]]));
 return {
  version:2, workspace:Journey.session.home==='home'?'my-home':'fictional-demo', property,
  assessment:assessment?{status:riskCurrent()?'Current':'Outdated',date:assessment.date,source:assessment.source,
   sourceDate:assessment.sourceDate,category:assessment.exposure.category,coverage:assessment.exposure.coverage,limitations:assessment.limitations}:null,
  current:selection?decision({selection,funding:activeFunding(),scope:activeScope()},'Current'):null,
  history:historicalDecisions(h).map(entry=>decision(entry,'Historical · outdated')),
  records:Object.fromEntries(Object.entries(h.records).filter(([id,r])=>r.installation || activeScope()?.ids.includes(id)).map(([id,r])=>[id,{
   status:Journey.recordStatus(r), installationDate:r.installation?.date, warrantyExpiry:r.installation?.warrantyExpiry,
   verifiedOn:r.verified?.date,evidence:r.evidence.map(e=>({type:e.type,origin:e.origin,hasFile:!!e.file})),
   maintenance:r.maintenance?{status:Journey.maintenanceStatus(r,journeyToday()),due:r.maintenance.due,
    completedOn:r.maintenance.completed?.date,hasDocumentedSource:!!r.maintenance.source}:null
  }])),
  historicalInstallations:(h.pastRecords || []).map(({id,record})=>({measure:id,status:Journey.recordStatus(record),installationDate:record.installation.date,verifiedOn:record.verified?.date})),
  quotes:h.quotes.map(q=>({status:quoteApplies(q,selection)?'Current':'Historical',measure:q.measure,total:q.total,
   origin:q.origin,configuration:q.configuration,validUntil:q.validUntil,scope:q.scope}))
 };
}

function homeLocationField() {
 return `<label>Assessment area<select required name="home_area"><option value="">Choose an area</option>${areas.map((a,i)=>
  `<option value="${i}" ${state.homeArea===String(i)?'selected':''}>${i===areas.length-1?'Outside York pilot or location undisclosed':esc(a.name)}</option>`).join('')}</select></label>`;
}
async function switchJourneyHome(id, navigate=true) {
 const saved=Journey.session.inputsByHome?.[id], demo=state.profiles.find(p=>p.id===id);
 Journey.session.home=id;
 clearTimeout(propertyApplyTimer);
 ++state.seq;
 invalidateLab();
 Object.assign(lab,{plans:[], originals:[], active:null, managed:true, signature:null});
 Object.assign(state,{profile:demo?structuredClone(demo.property):{epc:'unknown',need_age:'unknown',wall_type:'unknown',terrace_position:'unknown'},
  profileOrigin:demo?'demo':'manual', budget:demo?.budget ?? 10000, lon:demo?.lon,lat:demo?.lat,
  costOverrides:{},historyInput:null,plan:0,invalidDraft:false,pending:false,result:null,resultContext:null,
  scenario:'base',priority:'balanced',benefitScenario:'central',floodLayer:'rofrs',quoteMeasure:null,homeArea:''},saved || {});
 state.blankHome=!demo && !saved;
 syncStatus('');
 if (navigate) location.hash='property';
 if (!state.blankHome) await compute(false);
 else saveJourney();
 render();
}
