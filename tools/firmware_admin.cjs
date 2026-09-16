// Local IAM/CI tooling. Never expose this module to the browser or device API.
const {execFileSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {createRequire}=require('node:module');
const {Firestore}=require('../firebase/functions/node_modules/@google-cloud/firestore');
const {OAuth2Client}=require('../firebase/functions/node_modules/google-auth-library');
const {Storage}=require('../firebase/functions/node_modules/@google-cloud/storage');
const {OAuth2Client:StorageAuth}=createRequire(require.resolve('../firebase/functions/node_modules/@google-cloud/storage'))('google-auth-library');
const {hash,version,compare,BOARDS,validateManifest}=require('../firebase/functions/contract.cjs');
const ROOT=path.resolve(__dirname,'..'),PROJECT='digirdu-lights',REPO='nstielau/digirdu-lights';
const [action,arg,board,role]=process.argv.slice(2);
const cli=(name,args)=>execFileSync(name,args,{cwd:ROOT,encoding:'utf8',stdio:['ignore','pipe','pipe']});
async function main(){
 if(process.env.FIRESTORE_EMULATOR_HOST||process.env.STORAGE_EMULATOR_HOST)throw new Error('Unset emulators for production administration');
 const token=cli('gcloud',['auth','print-access-token']).trim();
 const auth=new OAuth2Client();auth.setCredentials({access_token:token});auth.quotaProjectId=PROJECT;
 const db=new Firestore({projectId:PROJECT,authClient:auth});
 try{
  if(action==='seed-admin'){
   const email=arg||'nick.stielau@gmail.com';
   await db.doc('admins/'+hash(email.trim().toLowerCase())).set({email,enabled:true,grantedAt:Date.now(),grantedBy:'project-iam'});
   console.log('Administrator seeded.');
  }else if(action==='enroll'){
   if(!/^[a-f0-9]{12,32}$/.test(arg||'')||!BOARDS.includes(board)||!['producer','consumer'].includes(role)||
     (board===BOARDS[1]&&role!=='consumer'))throw new Error('Invalid device identity/role');
   const folder=path.join(ROOT,'.artifacts/ota');fs.mkdirSync(folder,{recursive:true,mode:0o700});
   const output=path.join(folder,arg+'.json'),secret=crypto.randomBytes(32).toString('hex');
   // Exclusive local create avoids accidental rotation; failed enrollment leaves a recoverable local record.
   fs.writeFileSync(output,JSON.stringify({id:arg,token:secret,board,role,api:`https://${PROJECT}.firebaseapp.com/device-api/v1`}),{flag:'wx',mode:0o600});
   await db.doc('devices/'+arg).create({name:role+' '+arg.slice(-6),board,role,enabled:true,paused:false,
      pin:null,tokenHash:hash(secret),enrolledAt:Date.now()});
   console.log('Enrolled '+arg+'; credential saved to ignored '+output);
  }else if(action==='status'){
   const docs=await db.collection('devices').get();
   for(const doc of docs.docs){const d=doc.data();console.log(JSON.stringify({id:doc.id,board:d.board,role:d.role,
    enabled:d.enabled,pin:d.pin,paused:d.paused,lastCheckIn:d.lastCheckIn,report:d.report}));}
  }else if(action==='import-release'){
   if(!version(arg))throw new Error('Invalid version');
   const tag='firmware-v'+arg;
   const release=JSON.parse(cli('gh',['release','view',tag,'--repo',REPO,'--json','isDraft,isPrerelease,tagName']));
   if(release.isDraft||release.isPrerelease||release.tagName!==tag)throw new Error('Stable published release required');
   const commit=JSON.parse(cli('gh',['api','repos/'+REPO+'/commits/'+tag])).sha;
   const temp=fs.mkdtempSync(path.join(os.tmpdir(),'digirdu-release-'));
   try{
    cli('gh',['release','download',tag,'--repo',REPO,'--dir',temp]);
    const m=validateManifest(JSON.parse(fs.readFileSync(path.join(temp,'manifest.json'),'utf8')));
    if(m.version!==arg||m.git_commit!==commit)throw new Error('Release source mismatch');
    const files=[];
    for(const f of m.files){
     const data=fs.readFileSync(path.join(temp,f.name));
     const source=JSON.parse(cli('gh',['api',`repos/${REPO}/contents/${f.name}?ref=${commit}`]));
     if(data.length!==f.size||hash(data)!==f.sha256||source.encoding!=='base64'||!data.equals(Buffer.from(source.content,'base64')))
       throw new Error('Artifact differs from tagged source');
     files.push([f,data]);
    }
    const storageAuth=new StorageAuth();storageAuth.setCredentials({access_token:token});storageAuth.quotaProjectId=PROJECT;
    const storage=new Storage({projectId:PROJECT,authClient:storageAuth}),bucket=storage.bucket(PROJECT+'-firmware');
    for(const [f,data] of files){
     const file=bucket.file(`releases/${arg}/${m.sha256}/${f.name}`);
     try{await file.save(data,{resumable:false,validation:'crc32c',preconditionOpts:{ifGenerationMatch:0},
       metadata:{contentType:'application/octet-stream',cacheControl:'private,max-age=31536000,immutable'}});}
     catch(e){if(e.code!==412||hash((await file.download())[0])!==f.sha256)throw new Error('Immutable object mismatch');}
    }
    await db.runTransaction(async tx=>{
     const ref=db.doc('releases/'+arg),old=(await tx.get(ref)).data();
     const channel=db.doc('channels/stable'),current=(await tx.get(channel)).data();
     const counter=db.doc('control/sequence'),sequence=(await tx.get(counter)).data()?.value||0;
     if(old){if(JSON.stringify(old.manifest)!==JSON.stringify(m))throw new Error('Immutable release mismatch');return;}
     tx.create(ref,{manifest:m,approved:true,revoked:false,importedAt:Date.now()});
     if(!current||compare(arg,current.version)>0){tx.set(counter,{value:sequence+1});tx.set(channel,{version:arg,sequence:sequence+1});}
    });
    console.log('Imported immutable release '+arg+'; newest stable advanced if newer.');
   }finally{fs.rmSync(temp,{recursive:true,force:true});}
  }else throw new Error('Usage: seed-admin [EMAIL] | enroll ID BOARD ROLE | import-release VERSION | status');
 }finally{await db.terminate();}
}
main().catch(error=>{console.error('Firmware administration failed: '+(error.code||error.message||'unknown'));process.exitCode=1;});
