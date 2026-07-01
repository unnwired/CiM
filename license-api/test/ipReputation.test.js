import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { parseIpqsResponse, isBlockingEnabled } from '../src/ipReputation.ts';

describe('parseIpqsResponse', () => {
  it('flags VPN and proxy', () => {
    const r = parseIpqsResponse({ success: true, proxy: true, vpn: true, tor: false, hosting: false, fraud_score: 88 });
    assert.equal(r.vpn, true);
    assert.equal(r.proxy, true);
    assert.equal(r.shouldBlock, true);
    assert.ok(r.blockReasons.includes('vpn'));
  });

  it('flags tor and datacenter', () => {
    const r = parseIpqsResponse({ success: true, tor: true, active_tor: true, hosting: true });
    assert.equal(r.tor, true);
    assert.equal(r.datacenter, true);
    assert.ok(r.blockReasons.includes('tor'));
    assert.ok(r.blockReasons.includes('datacenter'));
  });

  it('clean residential IP does not block', () => {
    const r = parseIpqsResponse({ success: true, proxy: false, vpn: false, tor: false, hosting: false });
    assert.equal(r.shouldBlock, false);
    assert.equal(r.blockReasons.length, 0);
  });
});

describe('isBlockingEnabled', () => {
  it('reads BLOCK_ANONYMIZED_NETWORKS', () => {
    assert.equal(isBlockingEnabled({ BLOCK_ANONYMIZED_NETWORKS: '1' }), true);
    assert.equal(isBlockingEnabled({ BLOCK_ANONYMIZED_NETWORKS: 'true' }), true);
    assert.equal(isBlockingEnabled({}), false);
  });
});
