import { copy } from '@/content/copy';
export function formatPrice(amount: string | null, currency: string | null): string {
  if (amount === null || currency === null) return copy.priceOnRequest;
  try { return new Intl.NumberFormat(undefined,{style:'currency',currency}).format(Number(amount)); } catch { return `${currency} ${amount}`; }
}
export const isHttpsUrl = (value: string | null | undefined): value is string => Boolean(value?.startsWith('https://'));
export function locationText(items: readonly {name:string}[]): string { return items.map(x=>x.name).join(' › ') || copy.unknownLocation; }
