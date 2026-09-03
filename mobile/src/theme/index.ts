import { Platform } from 'react-native';

export const colors = {
  lime: '#9AC104', limeSoft: '#EEF6D5', primary: '#15583A', primaryDark: '#0B3525',
  primarySoft: '#E5F0EA', background: '#F7F5ED', surface: '#FFFFFF', surfaceWarm: '#FCFBF6',
  text: '#1C2923', muted: '#5F6C65', border: '#D7DED9', success: '#247548',
  warning: '#8B5D12', error: '#A23832', white: '#FFFFFF',
} as const;
export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48, xxxl: 64 } as const;
export const radii = { sm: 8, md: 14, lg: 22, xl: 30, pill: 999 } as const;
export const type = { display: 42, hero: 34, title: 26, heading: 20, body: 16, small: 14, label: 12 } as const;
export const touch = { minimum: 44 } as const;
export const layout = { maxContentWidth: 1200, phone: 600, desktop: 1024 } as const;
export type LayoutMode = 'phone' | 'tablet' | 'desktop';
export const layoutMode = (width: number): LayoutMode => width < layout.phone ? 'phone' : width < layout.desktop ? 'tablet' : 'desktop';
export const listingColumns = (width: number): number => layoutMode(width) === 'phone' ? 1 : layoutMode(width) === 'tablet' ? 2 : 3;
export const marketplaceColumns = (width: number): number => layoutMode(width) === 'desktop' ? 4 : layoutMode(width) === 'tablet' ? 2 : width >= 420 ? 2 : 1;
export const shadow = Platform.select({ android: { elevation: 3 }, default: { shadowColor: '#0B3525', shadowOpacity: 0.09, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } } });
