// Only bundled into ignored .artifacts/web-test. Never deployed.
let user=null,listener;
export const currentUser=()=>user;
export const onUser=callback=>{listener=callback;callback(user);};
export const signIn=async()=>{user={email:'owner@example.test'};await listener(user);};
export const signOut=async()=>{user=null;await listener(user);};
async function request(route,body){const r=await fetch('/test-api/'+route,{method:'POST',body:JSON.stringify(body||{})});if(!r.ok)throw new Error('test failure');return {data:await r.json()};}
export const overview=()=>request('overview');export const change=body=>request('change',body);
