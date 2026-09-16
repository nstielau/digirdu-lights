import {build} from 'esbuild';
import {mkdir,copyFile,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
const testing=process.argv.includes('--test'),out=testing?'.artifacts/web-test':'web/dist';
await rm(out,{recursive:true,force:true});await mkdir(out,{recursive:true});
await build({entryPoints:['web/app.js'],bundle:true,minify:true,format:'esm',outfile:out+'/app.js',
  plugins:testing?[{name:'test-gateway',setup(b){b.onResolve({filter:/^\.\/gateway\.js$/},()=>({path:resolve('web/test/gateway.js')}));}}]:[]});
for(const file of ['index.html','styles.css'])await copyFile('web/'+file,out+'/'+file);
