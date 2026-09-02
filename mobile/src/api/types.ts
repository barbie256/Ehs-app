export type TaxonomyLabel = Readonly<{ code: string; name: string }>;
export type Marketplace = TaxonomyLabel & Readonly<{ listing_count: number }>;
export type Category = TaxonomyLabel & Readonly<{ marketplace: string; parent: string | null; listing_count: number }>;
export type LocationNode = TaxonomyLabel & Readonly<{ parent: string | null; listing_count: number; children: readonly LocationNode[] }>;
export type PublicImage = Readonly<{ url: string; alt_text: string }>;
export type ListingSummary = Readonly<{
  id: string; title: string; slug: string; summary: string; marketplace: TaxonomyLabel; primary_category: TaxonomyLabel;
  location: TaxonomyLabel | null; price: string | null; currency: string | null; pricing_type: string; featured: boolean;
  rating: string | null; rating_count: number; primary_image: PublicImage | null; contact_available: boolean; source_url: string | null;
}>;
export type ListingDetail = ListingSummary & Readonly<{
  description: string; tagline: string | null; gallery: readonly PublicImage[]; categories: readonly TaxonomyLabel[];
  location_hierarchy: readonly TaxonomyLabel[]; source_modified_at: string | null;
}>;
export type ListingPage = Readonly<{ items: readonly ListingSummary[]; page: number; per_page: number; total: number; total_pages: number; has_next: boolean; has_previous: boolean }>;
export type ApiErrorKind = 'configuration' | 'network' | 'timeout' | 'unavailable' | 'validation' | 'server';
export class PublicApiError extends Error { constructor(public readonly kind: ApiErrorKind, message: string) { super(message); this.name = 'PublicApiError'; } }
export type ListingOrder = 'newest' | 'title' | 'rating';
export type SortDirection = 'asc' | 'desc';
export type ListingFilters = Readonly<{ page?: number; perPage?: number; marketplace?: string; category?: string; location?: string; q?: string; featured?: boolean; orderBy?: ListingOrder; order?: SortDirection }>;
