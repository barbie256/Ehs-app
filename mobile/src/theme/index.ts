import { Platform } from 'react-native';

export const colors = {
  primary: '#145A3B', primaryDark: '#0D3F2A', gold: '#C9982E', background: '#FAF8F1', surface: '#FFFFFF',
  text: '#252A28', muted: '#66706B', border: '#D9DED9', success: '#287A4B', warning: '#9A6515', error: '#A53A35', white: '#FFFFFF',
} as const;
export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 } as const;
export const radii = { sm: 8, md: 14, lg: 22, pill: 999 } as const;
export const type = { hero: 32, title: 24, heading: 20, body: 16, small: 14, label: 12 } as const;
export const touch = { minimum: 44 } as const;
export const shadow = Platform.select({ android: { elevation: 3 }, default: { shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 10, shadowOffset: { width: 0, height: 4 } } });
