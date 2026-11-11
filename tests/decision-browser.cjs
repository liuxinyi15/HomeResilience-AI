/* Static GitHub Pages subpath and Chromium regression. Run with Playwright on NODE_PATH. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {serve} = require('./static-site.cjs');
const {chromium} = require('playwright');

const root = path.resolve(__dirname, '..');
const output = process.env.DECISION_CASE_OUTPUT || path.join(root,'.test-output','decision-intelligence');
const cases = require('./fixtures/decision-cases.json');
async function ready(page, budget){
 await page.waitForFunction(n=>state.budget===n && lab.result?.budget===n &&
    document.querySelector('#lab-status')?.textContent.startsWith('All values match'), budget);
}
async function downloadFile(page, selector, destination){
 const [download] = await Promise.all([page.waitForEvent('download'),page.locator(selector).click()]);
 await download.saveAs(destination);
 return fs.readFile(destination,'utf8');
}

async function runCase(browser, url, demo){
 const {id,payload}=demo;
 const folder=path.join(output,id);
 await fs.mkdir(folder,{recursive:true});
 const page=await browser.newPage({viewport:id==='long-term'?{width:390,height:844}:{width:1440,height:1000}});
 const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',message=>{if(['error','warning'].includes(message.type()))errors.push(message.text());});
 const go=async route=>{
  const mobile=page.locator('#mobile-stage');
  if (await mobile.isVisible()) await mobile.selectOption(route);
  else await page.locator(`nav a[data-page="${route}"]`).click();
  await page.waitForFunction(route=>state.page===route,route);
 };
 const checks=[];
 try{
  await page.goto(url);
  await page.locator(`[data-profile="${id}"]`).first().click();
  await page.waitForURL('**/#property');
  await go('comparison');
  await ready(page,payload.budget);
  const original=await page.evaluate(()=>({
   budget:state.budget, analysis:state.result, comparison:lab.result, request:comparisonExport().input
  }));
  assert.equal(original.analysis.assessment.input_origin,'Synthetic demonstration profile');
  for(const [key,value] of Object.entries(payload.property))assert.equal(original.analysis.property[key],value);
  assert.deepEqual(original.comparison.plans.map(p=>p.name),original.analysis.packages.map(p=>p.name));
  assert.ok(original.comparison.plans.length>=1 && original.comparison.plans.length<=3);
  assert.equal(new Set(original.comparison.plans.map(p=>p.ids.join(','))).size,original.comparison.plans.length);
  assert.equal(original.analysis.budget_decisions.quality_status,'insufficient_comparable_evidence');
  for(const [i,plan] of original.comparison.plans.entries()){
   const strategy=original.analysis.budget_decisions.strategies[i];
   assert.deepEqual(plan.ids,strategy.ids);
   assert.equal(plan.cost,strategy.cost);
   assert.equal(plan.gas_savings.central_kwh,strategy.gas_savings.central_kwh);
   assert.deepEqual(plan.pathways.covered,strategy.pathways.covered);
   assert.equal(plan.stability.feasible_cases,strategy.stability.feasible_cases);
   assert.ok(await page.locator('#lab-results .strategy').nth(i).getByText(new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP',maximumFractionDigits:0}).format(plan.cost),{exact:true}).count());
  }
  assert.equal(await page.locator('.budget-strategy').count(),original.comparison.plans.length);
  assert.equal(await page.getByText('Where does the extra money go?',{exact:true}).count(),1);
  checks.push('Profile and rendered portfolios agree with the browser analysis and comparison engine');

  if(id==='starter'){
   const upgrade=original.analysis.budget_decisions.next_add_only_upgrade;
   assert.ok(upgrade.budget_required>payload.budget);
   const phase=page.locator('[data-upgrade="next_add_only"]');
   await phase.locator('..').locator('summary').click();
   await phase.click();
   await ready(page,upgrade.budget_required);
   await page.locator('#lab-budget-range').fill(String(payload.budget));
   await page.locator('#lab-budget-range').dispatchEvent('change');
   await ready(page,payload.budget);
   assert.deepEqual(await page.evaluate(()=>lab.result.plans[1].ids),upgrade.ids);
   await page.locator('#lab-load-budget').click();
   await ready(page,payload.budget);
   const originalIds=original.comparison.plans[0].ids;
   assert.ok(originalIds.every(x=>upgrade.ids.includes(x)));
   checks.push('Clicked computed upgrade threshold, then used the budget slider to restore £2,000');
  }
  if(id==='family'){
   await page.locator('[data-recommended-action="1"]').click();
   await page.waitForURL('**/#action');
   assert.equal(await page.evaluate(()=>pack().name),'Best Value');
   assert.equal(await page.evaluate(()=>pack().cost),original.analysis.packages[1].cost);
   await go('comparison');
   await ready(page,payload.budget);
   const productSection=page.locator('section.panel').filter({has:page.getByRole('heading',{name:'Product and installation quality'})});
   await productSection.getByText(/Passive flood door.*documented configurations/i).click();
   assert.ok(await productSection.getByText(/PVCu/i).first().isVisible());
   assert.ok(await productSection.getByText(/Timber/i).first().isVisible());
   await page.locator('[data-lab-duplicate="0"]').click();
   await ready(page,payload.budget);
   const draftIndex=original.comparison.plans.length;
   const edit=page.locator(`[data-lab-plan="${draftIndex}"]`);
   await edit.locator('[data-lab-detail="flood-door"] summary').click();
   for(const key of ['low','base','high'])await edit.locator(`[data-measure="flood-door"][data-lab-field="${key}"]`).fill('2700');
   await ready(page,payload.budget);
   await edit.locator('[data-lab-product="flood-door"]').selectOption('m3-timber-out');
   await ready(page,payload.budget);
   const fitted=await page.evaluate(i=>lab.result.plans[i].measures.find(m=>m.id==='flood-door'),draftIndex);
   assert.equal(fitted.product.record.id,'m3-timber-out');
   assert.equal(fitted.quality_evidence.indicative_cost,null);
   assert.equal(fitted.cost_base,2600);
   for(const key of ['low','base','high'])await edit.locator(`[data-measure="flood-door"][data-lab-field="${key}"]`).fill('2800');
   await ready(page,payload.budget);
   let delta=await page.evaluate(i=>lab.result.plans[i].difference,draftIndex);
   assert.equal(delta.cost,200);
   assert.equal(delta.energy_kwh,0);
   assert.equal(delta.measure_breakdown.find(m=>m.id==='flood-door').delta_gbp,200);
   const draught=edit.locator('[data-lab-measure="draught"]');
   await draught.uncheck();
   await ready(page,payload.budget);
   delta=await page.evaluate(i=>lab.result.plans[i].difference,draftIndex);
   assert.ok(delta.removed.includes('draught'));
   assert.equal(delta.energy_kwh,0);
   await page.locator('#lab-baseline').selectOption(String(draftIndex));
   await ready(page,payload.budget);
   assert.equal(await page.evaluate(()=>lab.result.plans[0].difference.cost),-delta.cost);
   await page.locator('#lab-baseline').selectOption('0');
   await ready(page,payload.budget);
   await page.locator('#lab-budget-number').fill('9900');
   await page.locator('#lab-budget-number').press('Tab');
   await ready(page,9900);
   assert.equal(await edit.count(),1);
   await page.locator('#lab-budget-number').fill('10000');
   await page.locator('#lab-budget-number').press('Enter');
   await ready(page,payload.budget);
   checks.push('Compared PVCu and timber evidence, entered an illustrative whole-work quote, removed a measure and preserved the draft across budget changes');
  }
  if(id==='long-term'){
   assert.ok(original.comparison.plans[0].cost<payload.budget);
   assert.ok(original.analysis.excluded.some(m=>m.id==='flood-door'));
   assert.equal(original.comparison.plans[0].lifecycle.totals_gbp,null);
   const edit=page.locator('[data-lab-plan="0"]');
   await edit.locator('[data-lifecycle-details] summary').click();
   await edit.locator('[data-lifecycle-field="years"]').fill('10');
   await edit.locator('[data-lifecycle-field="annual_maintenance_gbp"]').fill('120');
   await edit.locator('[data-lifecycle-field="replacements_gbp"]').fill('500');
   await edit.locator('[data-lifecycle-field="replacement_year"]').fill('8');
   await edit.locator('[data-lifecycle-field="discount_rate_pct"]').fill('4');
   await edit.locator('[data-lifecycle-field="complete_installed_scope"]').check();
   await ready(page,payload.budget);
   const life=await page.evaluate(()=>lab.result.plans[0].lifecycle);
   const expected=original.comparison.plans[0].cost+Array.from({length:10},(_,i)=>120/1.04**(i+1)).reduce((a,b)=>a+b,0)+500/1.04**8;
   assert.equal(life.totals_gbp.base,Math.round(expected*100)/100);
   assert.equal(life.evidence_class,'illustrative');
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
   checks.push('Validated depth deferral, unallocated budget, Unknown lifecycle and entered expenditure arithmetic at mobile width');
  }
  const final=await page.evaluate(()=>({input:comparisonExport().input,result:lab.result}));
  await page.locator('[data-lab-select="0"]').click();
  await page.waitForURL('**/#action');
  const markdown=await downloadFile(page,'#download-plan',path.join(folder,'action-plan.md'));
  assert.match(markdown,/Selected strategy: Recommended for your priorities/);
  assert.match(markdown,/Custom specifications and comparison/);
  const [event]=await Promise.all([page.waitForEvent('download'),page.locator('#download-json').click()]);
  const exported=JSON.parse(await fs.readFile(await event.path(),'utf8'));
  assert.deepEqual(exported.selected_package.ids,final.result.plans[0].ids);
  assert.equal(exported.selected_package.cost,final.result.plans[0].cost);
  assert.equal(exported.comparison.result.selected_index,0);
  assert.equal(exported.analysis.budget,payload.budget);
  await go('planner');
  if(id==='long-term')assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
  await page.locator('#budget-number').fill(String(payload.budget+1));
  await page.getByRole('button',{name:'Apply budget'}).click();
  await page.waitForFunction(n=>state.result.budget===n&&!state.pending,payload.budget+1);
  await go('action');
  await page.getByText('Previous decisions are outdated.',{exact:true}).waitFor();
  assert.equal(await page.locator('#download-plan').count(),0);
  await go('comparison');
  await ready(page,payload.budget+1);
  assert.equal(await page.evaluate(()=>activeSelection()),null);
  assert.deepEqual(errors,[]);
  checks.push('Downloaded action plan and evidence JSON in Chromium and checked selected IDs, budget and cost');
  const record={case:demo,checks,assessment:original.analysis.assessment,
      eligible_measure_ids:await page.evaluate(()=>state.catalogue.filter(m=>!state.result.excluded.some(x=>x.id===m.id)).map(m=>m.id)),
      excluded:original.analysis.excluded,budget_decisions:original.analysis.budget_decisions,
      initial_comparison:original.comparison, final_comparison:final, selected_package:exported.selected_package};
  await fs.writeFile(path.join(folder,'case.json'),JSON.stringify(record,null,2)+'\n');
  return {id,budget:payload.budget,selected_cost:exported.selected_package.cost,checks};
 }finally{await page.close();}
}

(async()=>{
 const server = await serve();
 let browser;
 try {
  const {url} = server;
  browser=await chromium.launch({executablePath:process.env.DECISION_CHROME||undefined,headless:true});
  const results=[];
  for(const demo of cases)results.push(await runCase(browser,url,demo));
  await fs.writeFile(path.join(output,'browser-tests.json'),JSON.stringify({browser:browser.version(),results},null,2)+'\n');
  console.log(JSON.stringify(results,null,2));
 }catch(e){console.error(e);process.exitCode=1;}
 finally{if(browser)await browser.close();server.close();}
})();
