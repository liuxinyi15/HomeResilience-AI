/* Maps the app's existing request contract to static files and a Python worker. */
const api = (() => {
 const base = document.baseURI;
 const files = {
  profiles:'demo/profiles.json', provenance:'processed/flood/manifest.json',
  catalogue:'processed/interventions-v2.json', effects:'processed/need-effects.json',
  'decision-evidence':'processed/decision-evidence.json', 'pfr-evidence':'processed/pfr-evidence.json',
  validation:'reports/validation.json', 'epc-validation':'reports/epc-validation.json',
  'decision-evaluation':'reports/decision-evaluation.json', 'energy-model':'reports/energy-model.json',
 };
 let worker, sequence = 0;
 const pending = new Map();
 const layers = new Map();
 async function read(path, compressed = false) {
  const response = await fetch(new URL('data/' + path, base));
  if (!response.ok) throw Error('Could not load ' + path + ' (HTTP ' + response.status + ').');
  if (!compressed) return response.json();
  return new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).json();
 }
 const manifest = () => read(files.provenance);
 const knownLayers = manifest();
 // Geography and provenance share the same request during startup.
 knownLayers.catch(() => {});
 function stop(error) {
  worker?.terminate();
  worker = null;
  for (const request of pending.values()) request.reject(error);
  pending.clear();
 }
 function run(operation, payload) {
  if (!worker) {
   worker = new Worker(new URL('engine-worker.mjs', base), {type:'module'});
   worker.onmessage = ({data:{id, result, error, fatal}}) => {
    if (fatal) { stop(Error(error)); return; }
    const request = pending.get(id);
    if (!request) return;
    pending.delete(id);
    if (error) request.reject(Error(error));
    else request.resolve(result);
   };
   worker.onerror = () => stop(Error('The browser calculation engine could not start. Serve the complete site over HTTP and try reloading.'));
  }
  const id = ++sequence;
  return new Promise((resolve, reject) => {
   pending.set(id, {resolve, reject});
   worker.postMessage({id, operation, payload});
  });
 }
 return async (url, payload) => {
  const [path, query] = url.split('?');
  const key = path.slice('/api/'.length);
  if (path !== '/api/' + key) throw Error('Unknown application request.');
  if (['analyse', 'compare', 'product-evidence'].includes(key)) return run(key, payload);
  if (key === 'provenance') return knownLayers;
  if (key === 'geography') {
   const layer = new URLSearchParams(query).get('layer') || 'rofrs';
   if (!Object.hasOwn((await knownLayers).layers, layer)) throw Error('Requested flood layer is unavailable.');
   if (!layers.has(layer)) {
    // Retain the overview and latest scenario rather than every display layer.
    for (const previous of layers.keys()) if (previous !== 'rofrs') layers.delete(previous);
    layers.set(layer, read('processed/flood/display/' + layer + '.geojson.gz', true).catch(error => {
     layers.delete(layer);
     throw error;
    }));
   }
   return layers.get(layer);
  }
  if (Object.hasOwn(files, key)) return read(files[key]);
  throw Error('Unknown application request.');
 };
})();
