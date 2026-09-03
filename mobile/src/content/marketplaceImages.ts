import type { ImageSourcePropType } from 'react-native';

// Bundled, explicitly approved marketplace photographs. No runtime website fetch.
export const marketplaceImages = {
  property: require('../../assets/marketplaces/property.jpg') as ImageSourcePropType,
  construction: require('../../assets/marketplaces/construction.jpg') as ImageSourcePropType,
  home_interior: require('../../assets/marketplaces/home-interior.jpg') as ImageSourcePropType,
  professional_services: require('../../assets/marketplaces/professional-services.jpg') as ImageSourcePropType,
} as const;
export const marketplaceFallback = require('../../assets/branding/ehs-mall-logo-mark-cropped.png') as ImageSourcePropType;
export const marketplaceTextOverlayOpacity = 0.78;
export function marketplaceImage(code: string): ImageSourcePropType | undefined {
  return Object.prototype.hasOwnProperty.call(marketplaceImages, code)
    ? marketplaceImages[code as keyof typeof marketplaceImages]
    : undefined;
}
