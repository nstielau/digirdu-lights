import {test,expect} from '@playwright/test';
const fleet={stable:{version:'1.1.0'},releases:[{version:'1.1.0',manifest:{git_commit:'abcdefff',minimum_base:'1.0.0',protocol_send:3}}],
 devices:[{id:'4133c5792f0a',name:'Consumer',board:'ESP32 V2',role:'consumer',enabled:true,report:{version:'1.0.0',base_version:'1.0.0',state:'current',protocol_send:3,protocol_receive:[3]},lastCheckIn:100000}]};
test.beforeEach(async({page})=>{
 await page.route('https://profiles.example.test/avatar.svg',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44"><rect width="44" height="44" fill="teal"/></svg>'}));
 await page.route('**/test-api/overview',route=>route.fulfill({json:fleet}));await page.goto('/');
});
test('separates installed and desired versions; signs out cleanly',async({page})=>{
 await page.getByText('Sign in with Google').click();await expect(page.locator('#devices')).toContainText('1.0.0');
 await expect(page.locator('#devices')).toContainText('1.1.0 (latest)');
 await expect(page.locator('body')).toHaveJSProperty('scrollWidth',await page.locator('body').evaluate(e=>e.clientWidth));
 await expect(page.getByText('Sign out',{exact:true})).toBeHidden();
 await page.getByRole('button',{name:'Open account menu'}).click();
 await page.getByText('Sign out',{exact:true}).click();await expect(page.locator('#fleet')).toBeHidden();
 await expect(page.locator('#profile')).toBeHidden();await expect(page.locator('#sign-in')).toBeFocused();
});
test('pin sends explicit version and fresh request ID',async({page})=>{
 let request;await page.route('**/test-api/change',async route=>{request=route.request().postDataJSON();await route.fulfill({json:{ok:true}});});
 await page.getByText('Sign in with Google').click();await page.getByText('Assign release').click();
 await expect(page.locator('#status')).toContainText('Saved.');expect(request.action).toBe('pin');expect(request.version).toBe('1.1.0');expect(request.requestId).toHaveLength(36);
});
test('failed mutation is not retried automatically',async({page})=>{
 let calls=0;await page.route('**/test-api/change',route=>{calls++;return route.fulfill({status:503,body:'unavailable'});});
 await page.getByText('Sign in with Google').click();await page.getByText('Pause updates').click();
 await expect(page.locator('#status')).toContainText('could not be confirmed');expect(calls).toBe(1);
});
test('device names render as text',async({page})=>{
 await page.route('**/test-api/overview',route=>route.fulfill({json:{...fleet,devices:[{...fleet.devices[0],name:'<img src=x onerror=alert(1)>'}]}}));
 await page.getByText('Sign in with Google').click();await expect(page.locator('h3')).toHaveText('<img src=x onerror=alert(1)>');await expect(page.locator('#devices img')).toHaveCount(0);
});
test('profile photo opens a keyboard-accessible account dropdown',async({page})=>{
 await page.getByText('Sign in with Google').click();
 const toggle=page.getByRole('button',{name:'Open account menu'});
 await expect(page.locator('#profile-photo')).toBeVisible();
 await expect(page.locator('#profile-photo')).toHaveJSProperty('naturalWidth',44);
 await toggle.focus();await page.keyboard.press('Enter');
 await expect(toggle).toHaveAttribute('aria-expanded','true');
 await expect(page.locator('#profile-menu')).toContainText('owner@example.test');
 await page.keyboard.press('ArrowDown');await expect(page.locator('#sign-out')).toBeFocused();
 await page.keyboard.press('Escape');await expect(page.locator('#profile-menu')).toBeHidden();await expect(toggle).toBeFocused();
 await toggle.click();await page.getByRole('heading',{name:'Devices',exact:true}).click();
 await expect(page.locator('#profile-menu')).toBeHidden();
});
test('unavailable photo falls back to initials',async({page})=>{
 await page.route('https://profiles.example.test/avatar.svg',route=>route.abort());
 await page.getByText('Sign in with Google').click();
 await expect(page.locator('#profile-initials')).toHaveText('TO');await expect(page.locator('#profile-photo')).toBeHidden();
 await page.getByRole('button',{name:'Open account menu'}).click();await expect(page.locator('#sign-out')).toBeVisible();
});
test('effects guide has direct navigation and shares the signed-in account',async({page})=>{
 await page.getByText('Sign in with Google').click();
 await page.getByRole('navigation',{name:'Main',exact:true}).getByRole('link',{name:'Effects'}).click();
 await expect(page).toHaveTitle('Effects · Digirdu Lights');
 for(const name of ['Spectrum','Ember','Aurora','Ripple'])await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
 await expect(page.locator('tbody tr')).toHaveCount(8);
 await expect(page.locator('body')).toHaveJSProperty('scrollWidth',await page.locator('body').evaluate(e=>e.clientWidth));
 await page.getByRole('button',{name:'Open account menu'}).click();await page.getByRole('button',{name:'Sign out',exact:true}).click();
 await page.getByRole('navigation',{name:'Main',exact:true}).getByRole('link',{name:'Fleet',exact:true}).click();
 await expect(page.locator('#fleet')).toBeHidden();await expect(page.locator('#sign-in')).toBeVisible();
});
test('effects guide works when opened directly without sign-in',async({page})=>{
 let requests=0;await page.route('**/test-api/**',route=>{requests++;return route.abort();});
 await page.goto('/effects.html');await expect(page.getByRole('heading',{name:'Spectrum',exact:true})).toBeVisible();
 await expect(page.locator('#sign-in')).toBeVisible();expect(requests).toBe(0);
});
test('saved replay plays, pauses, seeks and labels its synthetic tail',async({page})=>{
 await page.goto('/effects.html');
 const play=page.getByRole('button',{name:'Play replay',exact:true}), seek=page.getByRole('slider',{name:'Position'});
 await expect(play).toBeEnabled();await expect(page.locator('#replay-grids canvas')).toHaveCount(5);
 await expect(page.getByRole('heading',{name:'Chroma',exact:true})).toBeVisible();
 await expect(page.locator('.effect-notes')).toContainText('Keep effects 1–4 selected until every board reports 1.0.4');
 await expect(page.locator('body')).toHaveJSProperty('scrollWidth',await page.locator('body').evaluate(e=>e.clientWidth));
 await seek.fill('450');await seek.dispatchEvent('input');
 await expect(page.locator('#replay-section')).toHaveText('drone');
 await expect(page.locator('#replay-time')).toContainText('22.5');
 await play.click();await expect.poll(()=>seek.inputValue()).not.toBe('450');
 await page.getByRole('button',{name:'Pause replay'}).click();
 const paused=await seek.inputValue();await page.waitForTimeout(150);expect(await seek.inputValue()).toBe(paused);
 await seek.fill(await seek.getAttribute('max'));await seek.dispatchEvent('input');
 await expect(page.locator('#replay-section')).toContainText('synthetic fade (not recorded)');
 await play.click();await expect.poll(async()=>Number(await seek.inputValue())).toBeLessThan(100);
});
test('missing replay keeps the effect guide usable',async({page})=>{
 await page.route('**/effects-replay.json',route=>route.fulfill({status:503,body:'unavailable'}));
 await page.goto('/effects.html');
 await expect(page.locator('#replay-section')).toContainText('could not load');
 await expect(page.getByRole('button',{name:'Play replay'})).toBeDisabled();
 await expect(page.getByRole('heading',{name:'Chroma',exact:true})).toBeVisible();
});

async function routeReviewBundle(page,url='/gesture-review.json'){
 await page.route(`**${url}`,route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,
  audio_url:'/fixture.wav',
  waveform:[0,.2,.8,.3],
  labels:[{type:'drone',start_ms:200,end_ms:800}],
  events:[{type:'yell',time_ms:500,confidence:.9}],
  features:[{time_ms:500,volume:.8,drone:.7,vocal:.9,transient_strength:.2}],
  comparison:{},
  effects:{frames:{}}
 }}));
 await page.route('**/fixture.wav',route=>route.abort());
}

async function dragReviewWaveform(page,waveform,box,fromFraction,toFraction,browserName){
 const startX=box.x+box.width*fromFraction;
 const endX=box.x+box.width*toFraction;
 const clientY=box.y+40;
 if(browserName!=='webkit'){
  await page.mouse.move(startX,clientY);
  await page.mouse.down();
  await page.mouse.move(endX,clientY);
  await page.mouse.up();
  return;
 }
 await waveform.evaluate((node,{startX,endX,clientY})=>{
  const captured=new Set();
  node.setPointerCapture=pointerId=>captured.add(pointerId);
  node.hasPointerCapture=pointerId=>captured.has(pointerId);
  node.releasePointerCapture=pointerId=>captured.delete(pointerId);
  const dispatch=(type,clientX)=>node.dispatchEvent(new PointerEvent(type,{
   bubbles:true,cancelable:true,pointerId:17,pointerType:'touch',isPrimary:true,
   button:type==='pointermove'?-1:0,buttons:type==='pointerup'?0:1,clientX,clientY
  }));
  dispatch('pointerdown',startX);
  dispatch('pointermove',endX);
  dispatch('pointerup',endX);
 },{startX,endX,clientY});
}

test('review page synchronizes all tracks from one playhead',async({page})=>{
 await page.route('**/test-review.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,
  audio_url:'/fixture.wav',
  waveform:[0,.2,.8,.3],
  labels:[{type:'drone',start_ms:200,end_ms:800}],
  events:[{type:'yell',time_ms:500,confidence:.9}],
  features:[{time_ms:500,volume:.8,drone:.7,vocal:.9,transient_strength:.2}],
  comparison:{yell:{true_positive:1,false_positive:1,false_negative:0,precision:.5,recall:1,f1:2/3,timing_error_ms:[100],absolute_timing_error_ms:[100],unmatched_labels:[],unmatched_events:[]}},
  effects:{node_distances_mm:[0],frames:{Spectrum:{'0':[
   {time_ms:500,pixels_rgb:Array.from({length:8},()=>[1,2,3])}
  ]}}}
 }}));
 await page.route('**/fixture.wav',route=>route.abort());
 await page.goto('/review.html?data=/test-review.json');
 await expect(page.getByRole('slider',{name:'Position'})).toHaveAttribute('max','1000');
 await page.getByRole('slider',{name:'Position'}).fill('500');
 await page.getByRole('slider',{name:'Position'}).dispatchEvent('input');
 await expect(page.locator('#review-time')).toHaveText('0.50 s');
 await expect(page.locator('[data-track-cursor="waveform"]')).toHaveAttribute('data-time-ms','500');
 await expect(page.locator('#review-events')).toContainText('yell');
 await expect(page.locator('.event-overlay')).toHaveCount(1);
 await expect(page.locator('.event-overlay')).toHaveAttribute('data-active','true');
 await page.locator('.event-overlay').click();
 await expect(page.getByRole('slider',{name:'Position'})).toHaveValue('500');
 await expect(page.locator('#review-features')).toContainText('0.80');
 await expect(page.locator('#review-comparison')).toContainText('yell');
 await expect(page.locator('#review-comparison')).toContainText('50% precision');
 await expect(page.locator('#review-led')).toHaveAttribute('data-time-ms','500');
 const labelButton=page.locator('#review-labels button');
 await expect(labelButton).toHaveAttribute('data-active','true');
 await expect(page.locator('.label-overlay')).toHaveAttribute('data-active','true');
 await labelButton.click();
 await expect(labelButton).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('#review-selected-label')).toContainText('drone');
 await page.getByRole('button',{name:'Replay label'}).click();
 await expect(page.getByRole('slider',{name:'Position'})).toHaveValue('0');
 await page.getByRole('slider',{name:'Zoom'}).fill('4');
 await page.getByRole('slider',{name:'Zoom'}).dispatchEvent('input');
 await expect(page.locator('#review-waveform')).toHaveAttribute('data-zoom','4');
 await expect(page.locator('#review-time')).toHaveText('0.00 s');
 await expect(labelButton).toHaveAttribute('data-active','false');
 await expect(labelButton).toHaveAttribute('aria-pressed','true');
 await expect(page.locator('.label-overlay')).toHaveAttribute('data-active','false');
 await expect(page.locator('body')).toHaveJSProperty('scrollWidth',await page.locator('body').evaluate(e=>e.clientWidth));
});

test('review waveform click seeks and preserves playback state',async({page})=>{
 await page.addInitScript(()=>{
  window.reviewCurrentTimeWrites=[];
  Object.defineProperty(HTMLMediaElement.prototype,'currentTime',{
   configurable:true,
   get(){return this.reviewCurrentTimeValue||0;},
   set(value){this.reviewCurrentTimeValue=value;window.reviewCurrentTimeWrites.push(value);}
  });
  HTMLMediaElement.prototype.play=async function(){};
  HTMLMediaElement.prototype.pause=function(){};
 });
 await routeReviewBundle(page);
 await page.goto('/review.html?data=/gesture-review.json');
 await page.locator('#review-audio').evaluate(audio=>{
  Object.defineProperty(audio,'src',{configurable:true,value:'mock://audio'});
  document.querySelector('#review-play').disabled=false;
 });
 await page.getByRole('button',{name:'Play',exact:true}).click();
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await waveform.click({position:{x:box.width/2,y:40}});
 const soughtMs=Number(await page.getByRole('slider',{name:'Position'}).inputValue());
 expect(soughtMs).toBeGreaterThanOrEqual(495);
 expect(soughtMs).toBeLessThanOrEqual(505);
 await expect(page.getByRole('button',{name:'Pause',exact:true})).toBeVisible();
 const writes=await page.evaluate(()=>window.reviewCurrentTimeWrites);
 expect(writes).toHaveLength(1);
 expect(writes[0]).toBeCloseTo(.5,1);
});

test('review waveform drag pans when zoomed without seeking',async({page,browserName})=>{
 await routeReviewBundle(page);
 await page.goto('/review.html?data=/gesture-review.json');
 const position=page.getByRole('slider',{name:'Position'});
 await position.fill('400');
 await position.dispatchEvent('input');
 const zoom=page.getByRole('slider',{name:'Zoom'});
 await zoom.fill('4');
 await zoom.dispatchEvent('input');
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await dragReviewWaveform(page,waveform,box,.75,.25,browserName);
 expect(await waveform.evaluate(node=>node.scrollLeft)).toBeGreaterThan(0);
 await expect(position).toHaveValue('400');
});

test('review waveform separates shaky clicks from pans and stays bounded at 1x',async({page,browserName})=>{
 await routeReviewBundle(page);
 await page.goto('/review.html?data=/gesture-review.json');
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await dragReviewWaveform(page,waveform,box,.25,(box.width*.25+4)/box.width,browserName);
 expect(Number(await page.getByRole('slider',{name:'Position'}).inputValue())).toBeGreaterThan(250);
 await dragReviewWaveform(page,waveform,box,.75,.25,browserName);
 expect(await waveform.evaluate(node=>node.scrollLeft)).toBe(0);
});

test('review page playback advances displays without repeatedly seeking audio',async({page})=>{
 await page.addInitScript(()=>{
  window.reviewCurrentTimeWrites=[];
  Object.defineProperty(HTMLMediaElement.prototype,'currentTime',{
   configurable:true,
   get(){return this.reviewCurrentTimeValue||0;},
   set(value){this.reviewCurrentTimeValue=value;window.reviewCurrentTimeWrites.push(value);}
  });
  HTMLMediaElement.prototype.play=async function(){};
  HTMLMediaElement.prototype.pause=function(){};
 });
 await page.route('**/playback-review.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,waveform:[0,.5],labels:[],events:[],
  features:[{time_ms:250,volume:.5,drone:.4,vocal:.3,transient_strength:.2}],effects:{frames:{}}
 }}));
 await page.goto('/review.html?data=/playback-review.json');
 await page.locator('#review-audio').evaluate(audio=>{
  Object.defineProperty(audio,'src',{configurable:true,value:'mock://audio'});
  document.querySelector('#review-play').disabled=false;
 });
 await page.getByRole('button',{name:'Play',exact:true}).click();
 await page.locator('#review-audio').evaluate(audio=>{
  audio.reviewCurrentTimeValue=.25;
  audio.dispatchEvent(new Event('timeupdate'));
 });
 await expect(page.locator('#review-time')).toHaveText('0.25 s');
 expect(await page.evaluate(()=>window.reviewCurrentTimeWrites)).toEqual([]);
});

test('review page reports missing bundle instead of showing empty tracks',async({page})=>{
 await page.route('**/missing-review.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({status:503,body:'unavailable'}));
 await page.goto('/review.html?data=/missing-review.json');
 await expect(page.locator('#review-status')).toContainText('could not load');
});

test('review page reports audio failures after loading a bundle',async({page})=>{
 await page.route('**/audio-error-review.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,audio_url:'/broken.wav',waveform:[],labels:[],events:[],features:[],effects:{frames:{}}
 }}));
 await page.route('**/broken.wav',route=>route.fulfill({status:404,body:'missing'}));
 await page.goto('/review.html?data=/audio-error-review.json');
 await expect(page.locator('#review-status')).toContainText(/audio/i);
});
