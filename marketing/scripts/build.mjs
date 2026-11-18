import {cp, copyFile, mkdir, readFile, rm, stat, writeFile} from 'node:fs/promises';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {rolldown} from 'rolldown';

// Vite 8 uses Rolldown internally. Build directly to avoid the vulnerable
// Vite -> tinyglobby / fdir / picomatch dependency graph (ReDoS).
const root=resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dist=join(root, 'dist');
await rm(dist, {recursive:true, force:true});
await mkdir(join(dist, 'src'), {recursive:true});
await cp(join(root, 'public'), dist, {recursive:true});
for(const file of ['style.css', 'immersive.css']){
  await copyFile(join(root, 'src', file), join(dist, 'src', file));
}
// Preserve dynamic import() splitting: the large Three.js head remains lazy.
const bundle=await rolldown({input:join(root, 'src', 'main.js'), platform:'browser'});
try {
  await bundle.write({
    dir:join(dist, 'assets'),
    format:'es',
    entryFileNames:'main.js',
    chunkFileNames:'[name]-[hash].js',
    assetFileNames:'[name]-[hash][extname]',
    minify:true,
    sourcemap:false,
  });
} finally {
  await bundle.close();
}
let html=await readFile(join(root, 'index.html'), 'utf8');
const entry='<script type="module" src="/src/main.js"></script>';
if(!html.includes(entry))throw new Error('Marketing JS entry changed unexpectedly');
html=html.replace(entry, '<script type="module" src="/assets/main.js"></script>');
await writeFile(join(dist, 'index.html'), html);
const output=await stat(join(dist, 'assets', 'main.js'));
if(!output.isFile() || output.size===0)throw new Error('Marketing bundle missing');
console.log('Marketing Rolldown build (Vite/picomatch free) complete');
