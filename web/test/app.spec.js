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

const reviewAudioBase64='UklGRmQBAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YUABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==';
const hostedCatalog={schema_version:1,recordings:[
 {id:'drone-yell-10s',name:'Generated drone/yell fixture',duration_ms:1000,label_counts:{drone:1,yell:1},event_counts:{transient:1,yell:1}},
 {id:'high-yell-01',name:'High yell 01',duration_ms:2000,label_counts:{drone:1,yell:1},event_counts:{transient:1,yell:1}}
]};
function testSpectrogram(columns){
 return {min_frequency_hz:31.25,max_frequency_hz:8000,min_dbfs:-90,max_dbfs:0,
  rows:3,columns,frames:Array.from({length:columns},(_,column)=>[0,80+column*20,255-column*20])};
}
function hostedReview(id){
 const high=id==='high-yell-01';
 return {id,audio_mime_type:'audio/wav',audio_base64:reviewAudioBase64,bundle:{
  duration_ms:high?2000:1000,waveform:high?[0,.5,1,.25]:[0,.5,1],spectrogram:testSpectrogram(high?4:3),
  labels:[{type:'drone',start_ms:high?200:100,end_ms:high?1800:900},{type:'yell',start_ms:high?950:450,end_ms:high?1050:550}],
  events:[{type:'transient',time_ms:300},{type:'yell',time_ms:high?1000:500}],features:[],
  comparison:{yell:{true_positive:1,false_positive:0,false_negative:0,precision:1,recall:1,f1:1}},effects:{frames:{}}
 }};
}
async function routeHostedReviews(page){
 await page.route('**/test-api/review-catalog',route=>route.fulfill({json:hostedCatalog}));
 await page.route('**/test-api/review-recording',route=>route.fulfill({json:hostedReview(route.request().postDataJSON().id)}));
}

test('local review catalog populates and switches recordings without sign-in',async({page})=>{
 await page.route('**/local-review/catalog.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:hostedCatalog}));
 for(const entry of hostedCatalog.recordings){
  await page.route(`**/local-review/${entry.id}/bundle.json`,route=>route.fulfill({json:hostedReview(entry.id).bundle}));
  await page.route(`**/local-review/${entry.id}/audio.wav`,route=>route.fulfill({contentType:'audio/wav',body:Buffer.from(reviewAudioBase64,'base64')}));
 }
 await page.goto('/review.html?catalog=/local-review/catalog.json');
 const recording=page.getByRole('combobox',{name:'Recording'});
 await expect(recording.locator('option')).toHaveCount(2);
 await expect(recording.locator('option').first()).toHaveCSS('background-color','rgb(27, 18, 44)');
 await expect(recording.locator('option').first()).toHaveCSS('color','rgb(255, 255, 255)');
 await expect(recording).toHaveValue('drone-yell-10s');
 await expect(page.locator('#review-selected-recording')).toContainText('Generated drone/yell fixture');
 await expect(page.locator('#review-spectrogram')).toHaveAttribute('data-columns','3');
 await recording.selectOption('high-yell-01');
 await expect(page.locator('#review-selected-recording')).toContainText('High yell 01');
 await expect(page.locator('#review-spectrogram')).toHaveAttribute('data-columns','4');
 await expect(page.locator('#sign-in')).toHaveCount(0);
});

test('hosted review signs in, switches recordings, resets view state, and clears on sign-out',async({page})=>{
 await page.addInitScript(()=>{
  window.reviewObjectUrls={created:[],revoked:[]};
  const create=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);
  URL.createObjectURL=blob=>{const url=create(blob);window.reviewObjectUrls.created.push(url);return url;};
  URL.revokeObjectURL=url=>{window.reviewObjectUrls.revoked.push(url);return revoke(url);};
 });
 await routeHostedReviews(page);
 await page.goto('/review.html');
 await expect(page.locator('#review-protected')).toBeHidden();
 await page.getByRole('button',{name:'Sign in with Google'}).click();
 const recording=page.getByRole('combobox',{name:'Recording'});
 await expect(recording.locator('option')).toHaveCount(2);
 await expect(recording).toHaveValue('drone-yell-10s');
 await expect(page.locator('#review-selected-recording')).toContainText('Generated drone/yell fixture');
 await expect(page.locator('#review-spectrogram')).toHaveAttribute('data-columns','3');
 await expect(page.locator('#review-labels')).toContainText('0.45 s');
 const position=page.getByRole('slider',{name:'Position'}),zoom=page.getByRole('slider',{name:'Zoom'});
 await position.fill('500');await position.dispatchEvent('input');
 await zoom.fill('4');await zoom.dispatchEvent('input');
 await page.locator('#review-waveform').evaluate(node=>{node.scrollLeft=100;});
 await page.locator('#review-labels button').first().click();
 await page.getByRole('checkbox',{name:'Transient (1)'}).check();
 await recording.selectOption('high-yell-01');
 await expect(page.locator('#review-selected-recording')).toContainText('High yell 01');
 await expect(page.locator('#review-labels')).toContainText('0.95 s');
 await expect(page.locator('#review-spectrogram')).toHaveAttribute('data-columns','4');
 await expect(position).toHaveValue('0');
 await expect(zoom).toHaveValue('1');
 await expect(page.locator('#review-waveform')).toHaveJSProperty('scrollLeft',0);
 await expect(page.locator('#review-selected-label')).toHaveText('No label selected.');
 await expect(page.getByRole('checkbox',{name:'Transient (1)'})).not.toBeChecked();
 await page.getByRole('button',{name:'Open account menu'}).click();
 await page.getByRole('button',{name:'Sign out',exact:true}).click();
 await expect(page.locator('#review-protected')).toBeHidden();
 await expect(page.locator('#review-labels')).toBeEmpty();
 expect(await page.evaluate(()=>window.reviewObjectUrls)).toMatchObject({created:[expect.any(String),expect.any(String)],revoked:[expect.any(String),expect.any(String)]});
});

test('hosted review rejects unauthorized catalog access',async({page})=>{
 await page.route('**/test-api/review-catalog',route=>route.fulfill({status:403,body:'forbidden'}));
 await page.goto('/review.html');
 await page.getByRole('button',{name:'Sign in with Google'}).click();
 await expect(page.locator('#review-status')).toContainText('Administrator access is required');
 await expect(page.locator('#review-protected')).toBeHidden();
});

test('hosted review ignores a stale recording response',async({page})=>{
 let releaseFirst;
 const firstReady=new Promise(resolve=>{releaseFirst=resolve;});
 await page.route('**/test-api/review-catalog',route=>route.fulfill({json:hostedCatalog}));
 await page.route('**/test-api/review-recording',async route=>{
  const id=route.request().postDataJSON().id;
  if(id==='drone-yell-10s')await firstReady;
  await route.fulfill({json:hostedReview(id)});
 });
 await page.goto('/review.html');
 await page.getByRole('button',{name:'Sign in with Google'}).click();
 const recording=page.getByRole('combobox',{name:'Recording'});
 await expect(recording.locator('option')).toHaveCount(2);
 await recording.selectOption('high-yell-01');
 await expect(page.locator('#review-selected-recording')).toContainText('High yell 01');
 releaseFirst();
 await page.waitForTimeout(100);
 await expect(page.locator('#review-selected-recording')).toContainText('High yell 01');
});

async function routeReviewBundle(page,url='/gesture-review.json',overrides={}){
 const bundle={
  duration_ms:1000,
  audio_url:'/fixture.wav',
  waveform:[0,.2,.8,.3],
  spectrogram:testSpectrogram(4),
  labels:[{type:'drone',start_ms:200,end_ms:800}],
  events:[{type:'yell',time_ms:500,confidence:.9}],
  features:[{time_ms:500,volume:.8,drone:.7,vocal:.9,transient_strength:.2}],
  comparison:{},
  effects:{frames:{}},
  ...overrides,
 };
 await page.route(`**${url}`,route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:bundle}));
 await page.route('**/fixture.wav',route=>route.abort());
}

async function dragReviewWaveform(page,waveform,_box,fromFraction,toFraction,browserName){
 const box=await waveform.evaluate(node=>{
  node.scrollIntoView({block:'center'});
  const rect=node.getBoundingClientRect();
  return {x:rect.x,y:rect.y,width:rect.width};
 });
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
 const eventRow=page.locator('#review-events').getByRole('button',{name:'yell detected at 0.50 s'});
 await page.getByRole('slider',{name:'Position'}).fill('0');
 await page.getByRole('slider',{name:'Position'}).dispatchEvent('input');
 await eventRow.click();
 await expect(page.getByRole('slider',{name:'Position'})).toHaveValue('500');
 await page.getByRole('slider',{name:'Position'}).fill('0');
 await page.getByRole('slider',{name:'Position'}).dispatchEvent('input');
 await eventRow.press('Enter');
 await expect(page.getByRole('slider',{name:'Position'})).toHaveValue('500');
 await expect(eventRow).toBeFocused();
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

test('review stacks a log spectrogram under the waveform on the shared timeline',async({page})=>{
 await routeReviewBundle(page,'/spectrogram-review.json');
 await page.goto('/review.html?data=/spectrogram-review.json');
 const amplitude=page.locator('.waveform-region');
 const spectrogram=page.locator('.spectrogram-region');
 await expect(page.locator('#review-spectrogram')).toBeVisible();
 const amplitudeBox=await amplitude.boundingBox();
 const spectrogramBox=await spectrogram.boundingBox();
 expect(spectrogramBox.y).toBeGreaterThanOrEqual(amplitudeBox.y+amplitudeBox.height);
 expect(Math.abs(spectrogramBox.width-amplitudeBox.width)).toBeLessThanOrEqual(1);
 await expect(spectrogram).toContainText('8 kHz');
 await expect(spectrogram).toContainText('31 Hz');
 await expect(spectrogram).toContainText('-90 dBFS');
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await waveform.click({position:{x:box.width/2,y:spectrogramBox.y-box.y+spectrogramBox.height/2}});
 expect(Number(await page.getByRole('slider',{name:'Position'}).inputValue())).toBeGreaterThanOrEqual(495);
 await page.getByRole('slider',{name:'Zoom'}).fill('4');
 await page.getByRole('slider',{name:'Zoom'}).dispatchEvent('input');
 await expect(waveform).toHaveAttribute('data-zoom','4');
});

test('review event visibility filters known detector groups without changing evaluation',async({page})=>{
 await page.route('**/filter-review.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,waveform:[0,.5],
  labels:[{type:'drone',start_ms:100,end_ms:900}],
  events:[
   {type:'transient',time_ms:100},{type:'yell',time_ms:300},
   {type:'drone_start',time_ms:200},{type:'drone_stop',time_ms:800}
  ],
  features:[],comparison:{drone:{intersection_over_union:.7,false_active_ms:100,false_inactive_ms:200}},
  effects:{frames:{}}
 }}));
 await page.goto('/review.html?data=/filter-review.json');
 const transient=page.getByRole('checkbox',{name:'Transient (1)'});
 const yell=page.getByRole('checkbox',{name:'Yell (1)'});
 const drone=page.getByRole('checkbox',{name:'Drone boundaries (2)'});
 await expect(transient).not.toBeChecked();
 await expect(yell).toBeChecked();
 await expect(drone).toBeChecked();
 await expect(page.locator('#review-events li')).toHaveCount(3);
 await expect(page.locator('.event-overlay')).toHaveCount(3);
 await expect(page.locator('.label-overlay')).toHaveCount(1);
 const comparison=page.locator('#review-comparison');
 const comparisonText=await comparison.textContent();
 await transient.check();
 const eventBoxes=await page.locator('#review-events li').evaluateAll(items=>items.map(item=>item.getBoundingClientRect().toJSON()));
 expect(new Set(eventBoxes.map(box=>Math.round(box.y))).size).toBe(eventBoxes.length);
 expect(eventBoxes.every(box=>box.width===eventBoxes[0].width)).toBeTruthy();
 await drone.uncheck();
 await expect(page.locator('#review-events')).toContainText('transient');
 await expect(page.locator('#review-events')).toContainText('yell');
 await expect(page.locator('#review-events')).not.toContainText('drone_start');
 await expect(page.locator('.event-overlay')).toHaveCount(2);
 await expect(page.locator('.label-overlay')).toHaveCount(1);
 await expect(comparison).toHaveText(comparisonText);
});

test('review event visibility gives unknown types independent controls and preserves view state',async({page,browserName})=>{
 await page.route('**/unknown-filter-review.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,waveform:[0,.5],labels:[{type:'drone',start_ms:100,end_ms:900}],
  events:[{type:'raspy_burst',time_ms:600}],features:[],
  comparison:{yell:{true_positive:0,false_positive:0,false_negative:1,precision:0,recall:0,f1:0}},
  effects:{frames:{}}
 }}));
 await page.goto('/review.html?data=/unknown-filter-review.json');
 const position=page.getByRole('slider',{name:'Position'});
 await position.fill('400');
 await position.dispatchEvent('input');
 const zoom=page.getByRole('slider',{name:'Zoom'});
 await zoom.fill('4');
 await zoom.dispatchEvent('input');
 const waveform=page.locator('#review-waveform');
 const box=await waveform.boundingBox();
 await dragReviewWaveform(page,waveform,box,.75,.25,browserName);
 const scrollLeft=await waveform.evaluate(node=>node.scrollLeft);
 const comparison=page.locator('#review-comparison');
 const comparisonText=await comparison.textContent();
 const unknown=page.getByRole('checkbox',{name:'Raspy burst (1)'});
 await expect(unknown).toBeChecked();
 await unknown.uncheck();
 await expect(page.locator('#review-events')).toContainText('No detected events selected.');
 await expect(page.locator('.event-overlay')).toHaveCount(0);
 await expect(position).toHaveValue('400');
 await expect(waveform).toHaveAttribute('data-zoom','4');
 expect(await waveform.evaluate(node=>node.scrollLeft)).toBe(scrollLeft);
 await expect(page.locator('.label-overlay')).toHaveCount(1);
 await expect(comparison).toHaveText(comparisonText);
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

test('review explains when an older bundle has no spectrogram',async({page})=>{
 await routeReviewBundle(page,'/older-review.json',{spectrogram:undefined});
 await page.goto('/review.html?data=/older-review.json');
 await expect(page.locator('.spectrogram-empty')).toContainText('unavailable');
});

test('review rejects malformed spectrogram bytes',async({page})=>{
 await routeReviewBundle(page,'/invalid-spectrogram.json',{spectrogram:{
  ...testSpectrogram(4),frames:[[0,1,300],[0,1,2],[0,1,2],[0,1,2]]
 }});
 await page.goto('/review.html?data=/invalid-spectrogram.json');
 await expect(page.locator('#review-status')).toContainText('Review could not load: spectrogram values must be bytes');
});

test('review page reports audio failures after loading a bundle',async({page})=>{
 await page.route('**/audio-error-review.json',route=>route.request().resourceType()==='document'?route.continue():route.fulfill({json:{
  duration_ms:1000,audio_url:'/broken.wav',waveform:[],labels:[],events:[],features:[],effects:{frames:{}}
 }}));
 await page.route('**/broken.wav',route=>route.fulfill({status:404,body:'missing'}));
 await page.goto('/review.html?data=/audio-error-review.json');
 await expect(page.locator('#review-status')).toContainText(/audio/i);
});
