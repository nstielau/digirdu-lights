import test from 'node:test';
import assert from 'node:assert/strict';

import {localReviewDataUrl} from '../review-mode.mjs';

test('local review data URLs are accepted only on loopback hosts',()=>{
 assert.equal(localReviewDataUrl(new URL('http://localhost:8765/review.html?data=/take.json')),'/take.json');
 assert.equal(localReviewDataUrl(new URL('http://127.0.0.1:4174/review.html?data=/take.json')),'/take.json');
 assert.equal(localReviewDataUrl(new URL('https://digirdu-lights.firebaseapp.com/review.html?data=/take.json')),null);
 assert.equal(localReviewDataUrl(new URL('http://localhost:8765/review.html')),null);
});
