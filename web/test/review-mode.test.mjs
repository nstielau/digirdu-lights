import test from 'node:test';
import assert from 'node:assert/strict';

import * as reviewMode from '../review-mode.mjs';

const {localReviewDataUrl}=reviewMode;

test('local review data URLs are accepted only on loopback hosts',()=>{
 assert.equal(localReviewDataUrl(new URL('http://localhost:8765/review.html?data=/take.json')),'/take.json');
 assert.equal(localReviewDataUrl(new URL('http://127.0.0.1:4174/review.html?data=/take.json')),'/take.json');
 assert.equal(localReviewDataUrl(new URL('https://digirdu-lights.firebaseapp.com/review.html?data=/take.json')),null);
 assert.equal(localReviewDataUrl(new URL('http://localhost:8765/review.html')),null);
});

test('local review catalog URLs are accepted only on loopback hosts',()=>{
 assert.equal(typeof reviewMode.localReviewCatalogUrl,'function');
 assert.equal(reviewMode.localReviewCatalogUrl(new URL('http://localhost:8765/review.html?catalog=/review-data/catalog.json')),'/review-data/catalog.json');
 assert.equal(reviewMode.localReviewCatalogUrl(new URL('http://127.0.0.1:4174/review.html?catalog=/review-data/catalog.json')),'/review-data/catalog.json');
 assert.equal(reviewMode.localReviewCatalogUrl(new URL('https://digirdu-lights.firebaseapp.com/review.html?catalog=/review-data/catalog.json')),null);
 assert.equal(reviewMode.localReviewCatalogUrl(new URL('http://localhost:8765/review.html?data=/take.json')),null);
});

const effects={
 effects:['Spectrum','Ember','Chroma'],
 frames:{
  Spectrum:{'0':[{time_ms:0,pixels_rgb:[]}]},
  Ember:{'0':[{time_ms:0,pixels_rgb:[]}]},
  Chroma:{'0':[{time_ms:0,pixels_rgb:[]}]},
 }
};

test('review effects preserve declared order and preferred selection',()=>{
 assert.equal(typeof reviewMode.reviewEffectNames,'function');
 assert.equal(typeof reviewMode.selectReviewEffect,'function');
 assert.deepEqual(reviewMode.reviewEffectNames(effects),['Spectrum','Ember','Chroma']);
 assert.equal(reviewMode.selectReviewEffect(effects,'Chroma'),'Chroma');
 assert.equal(reviewMode.selectReviewEffect(effects,'Ripple'),'Spectrum');
});

test('review effect frames use virtual node zero and reject malformed rows',()=>{
 assert.equal(typeof reviewMode.reviewEffectFrames,'function');
 assert.equal(reviewMode.reviewEffectFrames(effects,'Ember'),effects.frames.Ember['0']);
 assert.deepEqual(reviewMode.reviewEffectFrames({frames:{Ember:{'0':{}}}},'Ember'),[]);
 assert.deepEqual(reviewMode.reviewEffectNames({frames:{Ripple:{'0':[]}}}),[]);
 assert.deepEqual(reviewMode.reviewEffectNames({frames:{Ripple:{'0':{}}}}),[]);
 assert.deepEqual(reviewMode.reviewEffectNames({frames:{Ripple:{'1':[{time_ms:0}]}}}),[]);
 assert.equal(reviewMode.selectReviewEffect({frames:{}},'Spectrum'),null);
});

test('review pixels clamp channels and darken malformed values',()=>{
 assert.equal(typeof reviewMode.reviewPixelChannels,'function');
 assert.deepEqual(reviewMode.reviewPixelChannels([300,-4,'bad']),[255,0,0]);
 assert.deepEqual(reviewMode.reviewPixelChannels({red:10}),[0,0,0]);
 assert.deepEqual(reviewMode.reviewPixelChannels(null),[0,0,0]);
});
