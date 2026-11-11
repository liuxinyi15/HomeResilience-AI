const {createServer} = require('node:http');
const {createReadStream} = require('node:fs');
const {stat} = require('node:fs/promises');
const {resolve, sep, extname} = require('node:path');

const prefix = '/HomeResilience-AI/';
const root = resolve(__dirname, '../site');
const mime = {
 '.html':'text/html; charset=utf-8', '.css':'text/css', '.js':'text/javascript',
 '.mjs':'text/javascript', '.json':'application/json', '.wasm':'application/wasm',
 '.zip':'application/zip', '.gz':'application/gzip', '.png':'image/png', '.csv':'text/csv',
};

async function serve() {
 const server = createServer(async (req, res) => {
  const pathname = new URL(req.url, 'http://example.test').pathname;
  if (pathname.startsWith(prefix)) {
   const path = resolve(root, pathname.slice(prefix.length) || 'index.html');
   const info = path.startsWith(root + sep) && await stat(path).catch(() => null);
   if (info?.isFile()) {
    res.writeHead(200, {'Content-Type':mime[extname(path)] || 'text/plain', 'Content-Length':info.size});
    createReadStream(path).pipe(res);
    return;
   }
  }
  res.writeHead(404).end('Not found');
 });
 await new Promise((resolve, reject) => {
  server.once('error', reject);
  server.listen(0, '127.0.0.1', resolve);
 });
 return {url:'http://127.0.0.1:' + server.address().port + prefix, close:() => server.close()};
}

module.exports = {serve};
