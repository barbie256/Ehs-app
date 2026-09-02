import AsyncStorage from '@react-native-async-storage/async-storage';
const KEY = 'ehs-mall:saved-listing-ids:v1';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export async function loadSavedIds(): Promise<string[]> {
  try { const value: unknown = JSON.parse((await AsyncStorage.getItem(KEY)) ?? '[]'); return Array.isArray(value) ? [...new Set(value.filter((x): x is string => typeof x === 'string' && UUID.test(x)))] : []; } catch { return []; }
}
export async function storeSavedIds(ids: readonly string[]): Promise<boolean> {
  try { await AsyncStorage.setItem(KEY, JSON.stringify([...new Set(ids.filter(x => UUID.test(x)))])); return true; } catch { return false; }
}
