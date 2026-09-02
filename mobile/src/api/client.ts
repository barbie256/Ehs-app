import { Platform } from 'react-native';
import { parseCategories, parseListingDetail, parseListingPage, parseLocations, parseMarketplaces } from './validation';
import type { Category, ListingDetail, ListingFilters, ListingPage, LocationNode, Marketplace } from './types';
import { PublicApiError } from './types';

const TIMEOUT_MS = 10_000;
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '10.0.2.2']);
export function validateBaseUrl(value: string | undefined): string {
  if (!value) throw new PublicApiError('configuration', 'The catalogue API is not configured.');
  let url: URL; try { url = new URL(value); } catch { throw new PublicApiError('configuration', 'The catalogue API configuration is invalid.'); }
  const privateLan = LOCAL_HOSTS.has(url.hostname) || /^192\.168\./.test(url.hostname) || /^10\./.test(url.hostname) || /^172\.(1[6-9]|2\d|3[01])\./.test(url.hostname);
  if (url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname) || (url.protocol !== 'https:' && !(url.protocol === 'http:' && privateLan))) throw new PublicApiError('configuration', 'The catalogue API configuration is not approved.');
  return url.origin;
}
export function listingQuery(filters: ListingFilters): string {
  const q = new URLSearchParams();
  if (filters.page) q.set('page', String(filters.page)); if (filters.perPage) q.set('per_page', String(filters.perPage));
  if (filters.marketplace) q.set('marketplace', filters.marketplace); if (filters.category) q.set('category', filters.category);
  if (filters.location) q.set('location', filters.location); if (filters.q?.trim()) q.set('q', filters.q.trim());
  if (filters.featured !== undefined) q.set('featured', String(filters.featured)); if (filters.orderBy) q.set('order_by', filters.orderBy); if (filters.order) q.set('order', filters.order);
  const value = q.toString(); return value ? `?${value}` : '';
}
async function request(path: string, signal?: AbortSignal): Promise<unknown> {
  const base = validateBaseUrl(process.env.EXPO_PUBLIC_API_BASE_URL); const controller = new AbortController();
  const timer = setTimeout(() => controller.abort('timeout'), TIMEOUT_MS); const abort = () => controller.abort('cancelled'); signal?.addEventListener('abort', abort, { once: true });
  try {
    const response = await fetch(`${base}${path}`, { method: 'GET', headers: { Accept: 'application/json' }, signal: controller.signal });
    if (response.status === 404) throw new PublicApiError('validation', 'This listing is unavailable.');
    if (response.status === 422) throw new PublicApiError('validation', 'The catalogue request was invalid.');
    if (response.status === 503) throw new PublicApiError('unavailable', 'The catalogue is temporarily unavailable.');
    if (!response.ok) throw new PublicApiError('server', 'The catalogue could not be loaded.');
    return await response.json() as unknown;
  } catch (error) {
    if (error instanceof PublicApiError) throw error;
    if (controller.signal.reason === 'timeout') throw new PublicApiError('timeout', 'The catalogue request timed out.');
    throw new PublicApiError('network', 'The catalogue could not be reached.');
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}
export const api = {
  marketplaces: async (s?: AbortSignal): Promise<Marketplace[]> => parseMarketplaces(await request('/api/v1/marketplaces', s)),
  categories: async (marketplace?: string, s?: AbortSignal): Promise<Category[]> => parseCategories(await request(`/api/v1/categories${marketplace ? `?${new URLSearchParams({ marketplace })}` : ''}`, s)),
  locations: async (s?: AbortSignal): Promise<LocationNode[]> => parseLocations(await request('/api/v1/locations', s)),
  listings: async (filters: ListingFilters, s?: AbortSignal): Promise<ListingPage> => parseListingPage(await request(`/api/v1/listings${listingQuery(filters)}`, s)),
  listing: async (id: string, s?: AbortSignal): Promise<ListingDetail> => parseListingDetail(await request(`/api/v1/listings/${encodeURIComponent(id)}`, s)),
};
export const runtimePlatform = Platform.OS;
