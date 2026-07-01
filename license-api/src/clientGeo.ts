export type ClientGeo = {
  ip: string | null;
  country: string | null;
  city: string | null;
  region: string | null;
};

type GeoBody = {
  client_ip?: string;
  client_country?: string;
  client_city?: string;
  client_region?: string;
};

function sanitizeIp(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const s = String(raw).trim();
  if (!s || s.length > 45) return null;
  if (!/^[\da-fA-F:.]+$/.test(s)) return null;
  return s;
}

function firstForwarded(xff: string | null): string | null {
  if (!xff) return null;
  return sanitizeIp(xff.split(',')[0]?.trim());
}

function sanitizeGeoField(raw: string | null | undefined, max = 120): string | null {
  if (!raw) return null;
  const s = String(raw).trim().slice(0, max);
  return s || null;
}

export function resolveClientGeo(request: Request, body?: GeoBody): ClientGeo {
  const bodyIp = sanitizeIp(body?.client_ip);
  const connectingIp =
    sanitizeIp(request.headers.get('cf-connecting-ip')) ||
    firstForwarded(request.headers.get('x-forwarded-for'));

  const ip = bodyIp || connectingIp || null;
  const cf = (request as Request & { cf?: IncomingRequestCfProperties }).cf;

  if (bodyIp) {
    return {
      ip: bodyIp,
      country: sanitizeGeoField(body?.client_country, 8),
      city: sanitizeGeoField(body?.client_city),
      region: sanitizeGeoField(body?.client_region),
    };
  }

  return {
    ip,
    country: sanitizeGeoField(cf?.country as string | undefined, 8),
    city: sanitizeGeoField(cf?.city as string | undefined),
    region: sanitizeGeoField((cf?.region || cf?.regionCode) as string | undefined),
  };
}
