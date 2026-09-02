import { useCallback, useEffect, useRef, useState } from 'react';
export type RequestState<T> = { data: T | null; loading: boolean; error: string | null; retry(): void };
export function useRequest<T>(load: (signal: AbortSignal) => Promise<T>, dependencies: readonly unknown[]): RequestState<T> {
  const [state,setState]=useState<Omit<RequestState<T>,'retry'>>({data:null,loading:true,error:null}); const [attempt,setAttempt]=useState(0); const sequence=useRef(0);
  const retry=useCallback(()=>setAttempt(x=>x+1),[]);
  useEffect(()=>{const current=++sequence.current;const controller=new AbortController();queueMicrotask(()=>{if(current===sequence.current)setState(s=>({...s,loading:true,error:null}));});load(controller.signal).then(data=>{if(current===sequence.current)setState({data,loading:false,error:null});}).catch(()=>{if(current===sequence.current&&!controller.signal.aborted)setState({data:null,loading:false,error:'Catalogue unavailable'});});return()=>controller.abort();},[attempt,...dependencies]); // eslint-disable-line react-hooks/exhaustive-deps
  return {...state,retry};
}
