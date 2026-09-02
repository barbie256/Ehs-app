import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { loadSavedIds, storeSavedIds } from '@/storage/saved';
type SavedState = { ids: readonly string[]; ready: boolean; storageError: boolean; isSaved(id: string): boolean; toggle(id: string): Promise<void> };
const Context = createContext<SavedState | null>(null);
export function SavedProvider({ children }: PropsWithChildren) {
  const [ids,setIds]=useState<readonly string[]>([]); const [ready,setReady]=useState(false); const [storageError,setStorageError]=useState(false);
  useEffect(()=>{ void loadSavedIds().then(value=>{setIds(value);setReady(true);}); },[]);
  const toggle=useCallback(async(id:string)=>{const next=ids.includes(id)?ids.filter(x=>x!==id):[...ids,id];setIds(next);setStorageError(!(await storeSavedIds(next)));},[ids]);
  const value=useMemo(()=>({ids,ready,storageError,isSaved:(id:string)=>ids.includes(id),toggle}),[ids,ready,storageError,toggle]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useSaved(): SavedState { const value=useContext(Context); if(!value) throw new Error('SavedProvider is required'); return value; }
