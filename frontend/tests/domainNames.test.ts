import assert from 'node:assert/strict';
import test from 'node:test';
import {domainName,readableText,errorTitle} from '../src/services/domainNames.ts';
test('internal identifiers in explanations and recovery messages use professional display names',()=>{
  assert.equal(domainName('A0'),'Mission planning Agent');
  assert.equal(domainName('A3'),'Radiation Exposure');
  const text=readableText('A0 needs A1 and A3. Update A_STELLAR_A0_MAX_REQUESTS. A0_BUDGET_EXHAUSTED');
  assert(text.includes('Terrain & Traversability') && text.includes('Radiation Exposure'));
  assert(!/\bA[0-6]\b|A0_/.test(text));
  assert.equal(errorTitle('A0_PROVIDER_ERROR'),'PLANNING PROVIDER ERROR');
  const original={agent_id:'A3',message:'A3 is missing'};
  readableText(original.message);
  assert.equal(original.agent_id,'A3');assert.equal(original.message,'A3 is missing');
});
