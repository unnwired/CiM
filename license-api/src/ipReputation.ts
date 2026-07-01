export type IpReputation = {
  proxy: boolean;
  vpn: boolean;
  tor: boolean;
  datacenter: boolean;
  fraudScore: number | null;
  shouldBlock: boolean;
  blockReasons: string[];
  lookupSkipped: boolean;
  lookupError: string | null;
};

export type IpReputationEnv = {
  IPQS_API_KEY?: string;
  BLOCK_ANONYMIZED_NETWORKS?: string;
  IP_REPUTATION_STRICTNESS?: string;
  IP_REPUTATION_FAIL_CLOSED?: string;
};

export type IpReputationDbFlags = {
  ip_proxy: number;
  ip_vpn: number;
  ip_tor: number;
  ip_datacenter: number;
  ip_fraud_score: number | null;
};

/** Parse IPQualityScore JSON response (exported for tests). */
export function parseIpqsResponse(data: Record<string, unknown>): Omit<IpReputation, 'lookupSkipped' | 'lookupError'> {
  const proxy = !!(data.proxy || data.active_vpn);
  const vpn = !!(data.vpn || data.active_vpn);
  const tor = !!(data.tor || data.active_tor);
  const datacenter = !!data.hosting;
  const fraudScore = typeof data.fraud_score === 'number' ? data.fraud_score : null;
  const blockReasons: string[] = [];
  if (proxy) blockReasons.push('proxy');
  if (vpn) blockReasons.push('vpn');
  if (tor) blockReasons.push('tor');
  if (datacenter) blockReasons.push('datacenter');
  return {
    proxy,
    vpn,
    tor,
    datacenter,
    fraudScore,
    shouldBlock: blockReasons.length > 0,
    blockReasons,
  };
}

export function isBlockingEnabled(env: IpReputationEnv): boolean {
  const raw = String(env.BLOCK_ANONYMIZED_NETWORKS ?? '').trim().toLowerCase();
  return raw === '1' || raw === 'true' || raw === 'yes';
}

export function reputationToDbFlags(rep: IpReputation): IpReputationDbFlags {
  return {
    ip_proxy: rep.proxy ? 1 : 0,
    ip_vpn: rep.vpn ? 1 : 0,
    ip_tor: rep.tor ? 1 : 0,
    ip_datacenter: rep.datacenter ? 1 : 0,
    ip_fraud_score: rep.fraudScore,
  };
}

function emptyReputation(overrides: Partial<IpReputation> = {}): IpReputation {
  return {
    proxy: false,
    vpn: false,
    tor: false,
    datacenter: false,
    fraudScore: null,
    shouldBlock: false,
    blockReasons: [],
    lookupSkipped: true,
    lookupError: null,
    ...overrides,
  };
}

export async function lookupIpReputation(
  ip: string | null | undefined,
  env: IpReputationEnv,
): Promise<IpReputation> {
  const trimmed = String(ip || '').trim();
  if (!trimmed) {
    return emptyReputation({ lookupError: 'no_ip' });
  }

  const apiKey = String(env.IPQS_API_KEY || '').trim();
  if (!apiKey) {
    return emptyReputation();
  }

  const strictness = Math.min(3, Math.max(0, parseInt(String(env.IP_REPUTATION_STRICTNESS || '1'), 10) || 1));
  const failClosed = String(env.IP_REPUTATION_FAIL_CLOSED || '').trim() === '1';

  try {
    const url = new URL(`https://ipqualityscore.com/api/json/ip/${apiKey}/${encodeURIComponent(trimmed)}`);
    url.searchParams.set('strictness', String(strictness));
    url.searchParams.set('allow_public_access_points', 'false');
    url.searchParams.set('fast', 'true');

    const res = await fetch(url.toString(), {
      headers: { 'User-Agent': 'CiM-License-API/1.0' },
    });
    if (!res.ok) {
      if (failClosed) {
        return emptyReputation({
          lookupSkipped: false,
          lookupError: `http_${res.status}`,
          shouldBlock: true,
          blockReasons: ['lookup_failed'],
        });
      }
      return emptyReputation({ lookupSkipped: false, lookupError: `http_${res.status}` });
    }

    const data = (await res.json()) as Record<string, unknown>;
    if (!data.success) {
      const msg = String(data.message || 'lookup_failed');
      if (failClosed) {
        return emptyReputation({
          lookupSkipped: false,
          lookupError: msg,
          shouldBlock: true,
          blockReasons: ['lookup_failed'],
        });
      }
      return emptyReputation({ lookupSkipped: false, lookupError: msg });
    }

    const parsed = parseIpqsResponse(data);
    return {
      ...parsed,
      lookupSkipped: false,
      lookupError: null,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'lookup_error';
    if (failClosed) {
      return emptyReputation({
        lookupSkipped: false,
        lookupError: msg,
        shouldBlock: true,
        blockReasons: ['lookup_failed'],
      });
    }
    return emptyReputation({ lookupSkipped: false, lookupError: msg });
  }
}

export function formatDenyReason(rep: IpReputation): string {
  if (rep.blockReasons.length) return rep.blockReasons.join(', ');
  return 'anonymized_network';
}
