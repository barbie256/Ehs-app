import AsyncStorage from '@react-native-async-storage/async-storage'; import { loadSavedIds,storeSavedIds } from '@/storage/saved'; import { formatPrice,isHttpsUrl,locationText } from '@/utils/format';
describe('local presentation and storage',()=>{
 beforeEach(()=>AsyncStorage.clear());
 test('stores UUIDs only and restores unique IDs',async()=>{const id='11111111-1111-4111-8111-111111111111';expect(await storeSavedIds([id,id,'not-id'])).toBe(true);expect(await loadSavedIds()).toEqual([id]);expect(await AsyncStorage.getItem('ehs-mall:saved-listing-ids:v1')).toBe(JSON.stringify([id]));});
 test('storage failures are controlled',async()=>{jest.spyOn(AsyncStorage,'getItem').mockRejectedValueOnce(new Error('storage'));expect(await loadSavedIds()).toEqual([]);jest.spyOn(AsyncStorage,'setItem').mockRejectedValueOnce(new Error('storage'));expect(await storeSavedIds([])).toBe(false);});
 test('does not assume UGX and uses price on request',()=>{expect(formatPrice(null,null)).toBe('Price on request');expect(formatPrice('12.50',null)).toBe('Price on request');expect(formatPrice('12.50','USD')).toContain('12.50');});
 test('accepts HTTPS images only',()=>{expect(isHttpsUrl('https://example.invalid/image.jpg')).toBe(true);expect(isHttpsUrl('http://example.invalid/image.jpg')).toBe(false);});
 test('renders canonical hierarchy without a default',()=>{expect(locationText([{name:'Africa'},{name:'Uganda'},{name:'Kampala'}])).toBe('Africa › Uganda › Kampala');expect(locationText([])).toBe('Location not specified');});
});
