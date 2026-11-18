import {createServer} from 'node:http';
import {readFile, stat} from 'node:fs/promises';
import {dirname, extname, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)), '..', 'dist');
const arg=process.argv.find(value=>value.startsWith('--port='));
const port=Number(arg?.slice(7) || process.env.PORT || 4173);
if(!Number.isInteger(port)||port<1||port>65535)throw new Error('Invalid preview port');
const mime={
  '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8',
  '.css':'text/css; charset=utf-8', '.json':'application/json; charset=utf-8',
  '.svg':'image/svg+xml', '.png':'image/png', '.jpg':'image/jpeg',
  '.jpeg':'image/jpeg', '.webp':'image/webp', '.avif':'image/avif',
  '.glb':'model/gltf-binary', '.gltf':'model/gltf+json',
  '.woff':'font/woff', '.woff2':'font/woff2', '.wasm':'application/wasm',
};
createServer(async(request,response)=>{
  if(request.method!=='GET' && request.method!=='HEAD'){
    response.writeHead(405,{'Allow':'GET, HEAD'}).end();
    return;
  }
  try {
    const path=decodeURIComponent(new URL(request.url,'http://localhost').pathname);
    if(path.includes(String.fromCharCode(0)))throw new Error('Invalid path');
    let target=resolve(root, '.'+path);
    if(target!==root&&!target.startsWith(root+sep))throw new Error('Outside dist');
    const info=await stat(target).catch(()=>null);
    if(info?.isDirectory()||path.endsWith('/'))target=resolve(target,'index.html');
    if(target!==root&&!target.startsWith(root+sep))throw new Error('Outside dist');
    const body=await readFile(target);
    response.writeHead(200,{
      'Content-Type':mime[extname(target)]||'application/octet-stream',
      'Cache-Control':target.endsWith('.html')?'no-store':'public, max-age=3600',
      'X-Content-Type-Options':'nosniff',
    });
    response.end(request.method==='HEAD'?undefined:body);
  } catch {
    response.writeHead(404,{'Content-Type':'text/plain; charset=utf-8','X-Content-Type-Options':'nosniff'});
    response.end('Not found');
  }
}).listen(port,'127.0.0.1',()=>console.log('Marketing preview http://127.0.0.1:'+port));
