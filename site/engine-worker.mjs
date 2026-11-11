import {loadPyodide} from './runtime/pyodide.mjs';

const indexURL = new URL('./runtime/', import.meta.url).href;
const modules = [
 '__init__', 'applicability', 'climate', 'comparison', 'decision_intelligence',
 'energy', 'engine', 'flood', 'impacts', 'pfr', 'quality', 'retrofit',
];
const dataFiles = [
 'data/processed/flood/manifest.json', 'data/processed/interventions-v2.json',
 'data/processed/need-effects.json', 'data/processed/decision-evidence.json',
 'data/processed/pfr-evidence.json', 'data/processed/product-evidence.json',
 'data/processed/quality-evidence-v1.json', 'models/gas-history.json',
 'models/gas2024-detail-lookup.json', 'models/gas2024-lookup.json',
];
const baseLayers = ['rofrs', 'depth_defended_100'];
const climateLayers = [
 ...baseLayers, 'present_defended_100', 'present_undefended_100',
 'future_defended_100', 'future_undefended_100',
];
let engine;
let queue = Promise.resolve();
const mountedLayers = new Set();

async function mount(py, path, compressed = false) {
 const url = new URL(path + (compressed ? '.gz' : ''), import.meta.url);
 const response = await fetch(url);
 if (!response.ok) throw Error('Could not load ' + path + ' (HTTP ' + response.status + ').');
 const bytes = compressed
  ? await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer()
  : await response.arrayBuffer();
 const target = '/app/' + path;
 py.FS.mkdirTree(target.slice(0, target.lastIndexOf('/')));
 py.FS.writeFile(target, new Uint8Array(bytes));
}
async function initialize() {
 const py = await loadPyodide({indexURL});
 await Promise.all([
  ...modules.map(name => 'src/homeresilience/' + name + '.py'),
  ...dataFiles,
 ].map(path => mount(py, path)));
 py.runPython(`
import sys, json
sys.path.insert(0, '/app/src')
from homeresilience.engine import analyse
from homeresilience.comparison import compare, product_evidence
from homeresilience.flood import manifest

def dispatch(operation, payload):
    try:
        if operation == 'product-evidence':
            result = product_evidence()
        else:
            fn = {'analyse': analyse, 'compare': compare}[operation]
            result = fn(json.loads(payload))
        return json.dumps({'result': result}, allow_nan=False)
    except (ValueError, TypeError, KeyError) as exc:
        return json.dumps({'error': str(exc)})
 `);
 return py;
}
async function respond({id, operation, payload}) {
 let py;
 try {
  py = await (engine ??= initialize());
 } catch (error) {
  self.postMessage({id, fatal:true, error:'Unable to initialize the calculation engine: ' + error.message});
  return;
 }
 try {
  if (operation !== 'product-evidence') {
   const required = new Set(operation === 'analyse' ? climateLayers : baseLayers);
   const manifest = JSON.parse(py.runPython('json.dumps(manifest())'));
   const selected = payload?.flood_layer;
   if (operation === 'analyse' && typeof selected === 'string' && Object.hasOwn(manifest.layers, selected)) required.add(selected);
   // Keep the core pilot files and at most one optional analysis layer in memory.
   for (const layer of mountedLayers) if (!climateLayers.includes(layer) && !required.has(layer)) {
    py.FS.unlink('/app/' + manifest.layers[layer].path);
    mountedLayers.delete(layer);
   }
   await Promise.all([...required].filter(layer => !mountedLayers.has(layer)).map(async layer => {
    await mount(py, manifest.layers[layer].path, true);
    mountedLayers.add(layer);
   }));
  }
  const dispatch = py.globals.get('dispatch');
  try {
   self.postMessage({id, ...JSON.parse(dispatch(operation, JSON.stringify(payload ?? null)))});
  } finally {
   dispatch.destroy();
  }
 } catch (error) {
  self.postMessage({id, error: 'The demo could not calculate this result: ' + error.message});
 }
}
self.onmessage = ({data}) => { queue = queue.then(() => respond(data)); };
