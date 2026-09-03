import { useRouter } from 'expo-router';
import { useEffect,useState } from 'react';
import { StyleSheet,Text,View } from 'react-native';
import type { ListingSummary } from '@/api/types';
import { api } from '@/api/client';
import { ListingList } from '@/components/catalogue';
import { Action,Empty,ErrorState,Header,Loading,PageIntro,Screen } from '@/components/ui';
import { useSaved } from '@/state/SavedContext';
import { colors,spacing,type } from '@/theme';

export default function Saved(){
 const saved=useSaved();const router=useRouter();const [items,setItems]=useState<ListingSummary[]>([]);const [loading,setLoading]=useState(true);const [error,setError]=useState(false);
 useEffect(()=>{const controller=new AbortController();queueMicrotask(()=>setLoading(true));Promise.allSettled(saved.ids.map(id=>api.listing(id,controller.signal))).then(results=>{if(!controller.signal.aborted){setItems(results.flatMap(result=>result.status==='fulfilled'?[result.value]:[]));setError(false);setLoading(false);}}).catch(()=>{if(!controller.signal.aborted){setError(true);setLoading(false);}});return()=>controller.abort();},[saved.ids]);
 const explore=()=>router.push('/(tabs)/explore');
 return <Screen><Header/><PageIntro eyebrow="Saved" title="Your shortlist" description="Keep the listings you like close at hand on this device."/>
  {loading||!saved.ready?<Loading label="Loading saved listings"/>:error||saved.storageError?<ErrorState onRetry={()=>setError(false)}/>:items.length?<View style={styles.content}><Text accessibilityRole="header" style={styles.count}>{items.length} saved {items.length===1?'listing':'listings'}</Text><ListingList items={items}/></View>:<Empty branded message="Your shortlist is ready when you are" description="Save listings as you browse, then return here to compare them." action={<Action label="Explore listings" onPress={explore}/>}/>}</Screen>;
}
const styles=StyleSheet.create({content:{gap:spacing.md},count:{fontSize:type.heading,fontWeight:'900',color:colors.primaryDark,paddingHorizontal:spacing.sm}});
