'use strict';

const Journey = (() => {
 const key = 'homeresilience.journey.v1';
 const fresh = () => ({quotes: [], records: {}, selection: null, funding: null, scope: null, assessment: null, triggers: []});
 const session = {save:false,home:'home',homes:{},inputsByHome:{}};
 function load(storage) {
  try {
   const saved = JSON.parse(storage.getItem(key));
   if ([1,2].includes(saved?.version) && saved.homes) {
    Object.assign(session,{home:saved.home,homes:saved.homes,inputsByHome:saved.inputsByHome || {},save:true});
    if (saved.version===1 && session.inputsByHome.home?.profileOrigin==='demo') {
     session.homes.legacySample=session.homes.home;
     delete session.homes.home;
     delete session.inputsByHome.home;
    }
   }
  } catch (_) { /* Browser storage may be unavailable. */ }
  return session;
 }
 function persist(storage) {
  try {
   if (session.save) storage.setItem(key, JSON.stringify({...session, version: 2}));
   else storage.removeItem(key);
   return true;
  } catch (_) { return false; }
 }
 function current() {
  return session.homes[session.home] ||= fresh();
 }
 function reportedCompleted(home, location) {
  return Object.entries(home.records).filter(([, record]) =>
   record.installation && (!location || !record.location || record.location===location) && (record.category !== 'Survey' || record.verified)).map(([id]) => id).sort();
 }
 function selected(home, context) {
  return context && home.selection?.context===context && !home.selection.outdated ? home.selection : null;
 }
 function dependent(record, parent) {
  return parent && record?.selection===parent.key && !record.outdated ? record : null;
 }
 function invalidate(home, context, reason='Property, risk or planning inputs changed.') {
  if (home.selection && !selected(home, context)) {
   for (const record of [home.selection,home.funding,home.scope]) {
    if (record) record.outdated ||= reason;
   }
  }
 }
 function archive(home, reason) {
  if (home.selection) (home.history ||= []).push({selection:home.selection,funding:home.funding,scope:home.scope,
   reason:home.selection.outdated || reason || 'A different portfolio was confirmed.'});
 }
 function status(home, context, risk, today) {
  const selection=selected(home,context), funding=dependent(home.funding,selection);
  const scope=funding && dependent(home.scope,selection) && home.scope.fundingKey===funding.key;
  const records=Object.values(home.records), project=scope?home.scope.ids.map(id=>home.records[id]):records.filter(r=>r.installation);
  const maintenance=records.filter(r=>r.installation && r.category!=='Survey').map(r=>maintenanceStatus(r,today));
  return {
   property:risk?'Complete':home.assessment?'Outdated':'Not started',
   planner:context?'Complete':home.assessment?'Outdated':'Not started',
   comparison:selection?'Complete':home.selection?'Outdated':context?'Ready':'Not started',
   funding:funding?'Complete':home.funding?'Outdated':'Not started',
   action:scope?'Complete':home.scope?'Outdated':'Not started',
   verify:project.length && project.every(r=>recordStatus(r)==='Verified')?'Complete':project.length?'In progress':'Not started',
   passport:records.some(r=>r.installation && recordStatus(r)!=='Verified')?'Evidence pending':home.assessment || records.length?'Record created':'No record',
   maintenance:maintenance.includes('Overdue')?'Overdue':maintenance.includes('Due')?'Due':maintenance.includes('No schedule available')?'No schedule':maintenance.length?'Current':'Future'
  };
 }
 const scopeFields = {
  product: 'Product', installation: 'Installation', vat: 'VAT', survey: 'Survey',
  removal: 'Removal and disposal', adaptation: 'Aperture adaptation',
  maintenance: 'Maintenance', warranty: 'Warranty documentation'
 };
 function compareQuotes(a, b, today, {keys=Object.keys(scopeFields), configuration=true}={}) {
  const unknown = keys.filter(k => ![a,b].every(q => ['included','excluded'].includes(q.scope[k])));
  const different = keys.filter(k => !unknown.includes(k) && a.scope[k] !== b.scope[k]);
  const gaps = unknown.map(k => scopeFields[k] + ' scope');
  if (configuration && (!a.configuration || !b.configuration)) gaps.push('configuration');
  if (!a.validUntil || !b.validUntil) gaps.push('validity date');
  if ([a,b].some(q => q.validUntil && q.validUntil < today)) gaps.push('expired quote');
  if (a.configuration && b.configuration && a.configuration !== b.configuration) different.push('configuration');
  return {
   delta: Math.round((b.total - a.total) * 100) / 100,
   gaps, different: different.map(k => scopeFields[k] || k),
   comparable: !gaps.length && !different.length && a.origin === b.origin
  };
 }
 function finance(cost, contribution, months, annualRate) {
  const principal = Math.max(0, cost - contribution);
  const rate = annualRate / 1200;
  const monthly = rate ? principal * rate / -Math.expm1(-months * Math.log1p(rate)) : principal / months;
  return {principal, monthly, total: monthly * months};
 }
 function stages(measures, upfront, scenario, completed = []) {
  // Work backwards from the chosen scope: every milestone is a subset of that plan.
  const cost = items => Math.round(items.reduce((sum, m) => sum + m['cost_' + scenario], 0) * 100) / 100;
  const phase = (items, added) => ({ids: items.map(m => m.id), added: added.map(m => m.id), cost: cost(items), kind: 'add_only'});
  const chosen = [], available = new Set(completed), remaining = [...measures];
  while (true) {
   const index = remaining.findIndex(m => m.requires.every(id => available.has(id)) && cost([...chosen, m]) <= upfront);
   if (index === -1) break;
   const [measure] = remaining.splice(index, 1);
   chosen.push(measure);
   available.add(measure.id);
  }
  const milestones = [phase(chosen, chosen)];
  // Separate enabling work where it was not affordable in the first stage.
  const enabling = remaining.filter(m => !m.requires.length && remaining.some(item => item.requires.includes(m.id)));
  const flood = remaining.filter(m => m.category === 'Flood' && m.requires.every(id => available.has(id)));
  const intermediate = flood.length ? flood : enabling;
  if (intermediate.length && intermediate.length < remaining.length) milestones.push(phase([...chosen, ...intermediate], intermediate));
  const later = remaining.filter(m => !milestones.slice(1).some(step => step.ids.includes(m.id)));
  if (remaining.length) milestones.push(phase(measures, later));
  return milestones;
 }
 function verificationGaps(record) {
  if (!record.installation) return ['Installation or survey completion details'];
  const required = record.category === 'Survey' ? ['report'] : ['completion', 'invoice'];
  if (record.category !== 'Survey' && (record.configuration || record.installation.configuration || record.installation.product)) required.push('certificate');
  return required.filter(type => !record.evidence?.some(item => item.type === type));
 }
 function recordStatus(record) {
  if (record.verified && !verificationGaps(record).length) return 'Verified';
  if (record.reviewed) return 'Verification incomplete';
  if (record.installation) return record.evidence?.length ? 'Evidence supplied' : 'Installed';
  return record.progress || 'Planned';
 }
 function maintenanceStatus(record, today) {
  const schedule = record.maintenance;
  if (!schedule?.source) return 'No schedule available';
  if (!schedule.due) return schedule.completed ? 'Completed' : schedule.professional ? 'Professional service required' : 'Schedule documented';
  if (schedule.due < today) return 'Overdue';
  if (schedule.due === today) return 'Due';
  const days = (Date.parse(schedule.due) - Date.parse(today)) / 86400000;
  return days <= 30 ? 'Upcoming' : 'Schedule documented';
 }
 return {session, fresh, load, persist, current, reportedCompleted, status, selected, dependent, invalidate, archive, scopeFields, compareQuotes,
  finance, stages, verificationGaps, recordStatus, maintenanceStatus};
})();
if (typeof module !== 'undefined') module.exports = Journey;
