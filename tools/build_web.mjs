import {build} from 'esbuild';
import {mkdir,copyFile,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
const testing=process.argv.includes('--test'),out=testing?'.artifacts/web-test':'web/dist';
await rm(out,{recursive:true,force:true});await mkdir(out,{recursive:true});
await build({entryPoints:['web/app.js','web/effects-page.js','web/review-online.js'],bundle:true,minify:true,format:'esm',outdir:out,
  plugins:testing?[{name:'test-gateway',setup(b){b.onResolve({filter:/^\.\/gateway\.js$/},()=>({path:resolve('web/test/gateway.js')}));}}]:[]});
for(const file of ['index.html','effects.html','review.html','styles.css'])await copyFile('web/'+file,out+'/'+file);
await copyFile('web/review-page.js',out+'/review-page.js');
await copyFile('web/review-mode.mjs',out+'/review-mode.mjs');
await copyFile('web/review-local.js',out+'/review-local.js');
await mkdir(out+'/assets',{recursive:true});
for(const file of ['laser-horizon.png','effects-replay.json'])await copyFile('web/assets/'+file,out+'/assets/'+file);
