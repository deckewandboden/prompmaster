import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const [file,expected]=process.argv.slice(2);
if(!file||!expected||!/^[a-f0-9]{64}$/i.test(expected)){
  console.error('Aufruf: node scripts/verify-golden-master.mjs ORIGINAL_DATEI ERWARTETER_SHA256');
  process.exit(2);
}
const actual=createHash('sha256').update(await readFile(file)).digest('hex');
if(actual!==expected.toLowerCase()){console.error('Golden Master verändert: '+actual);process.exit(1)}
console.log('Golden Master unverändert: '+actual);
