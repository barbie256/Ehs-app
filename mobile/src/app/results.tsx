import { useLocalSearchParams,useRouter } from 'expo-router';
import { StyleSheet,Text,View } from 'react-native';
import { api } from '@/api/client';
import { ListingList } from '@/components/catalogue';
import { Action,Empty,ErrorState,Header,Loading,PageIntro,Screen } from '@/components/ui';
import { useRequest } from '@/hooks/useRequest';
import { colors,spacing } from '@/theme';

export default function Results(){
 const params=useLocalSearchParams<{marketplace?:string;category?:string;title?:string}>();const router=useRouter();
 const state=useRequest(signal=>api.listings({marketplace:params.marketplace,category:params.category},signal),[params.marketplace,params.category]);
 const context=[params.title,params.category?.replaceAll('_',' ')].filter(Boolean).join(' · ')||'All marketplaces';
 const refine=()=>router.push({pathname:'/(tabs)/explore',params:{marketplace:params.marketplace,category:params.category}});
 return <Screen><Header/><PageIntro eyebrow="Catalogue results" title={params.title??'Discover listings'} description={`Showing ${context}`} aside={<Action label="Refine filters" onPress={refine}/>}/>
  {state.loading?<Loading label="Loading results"/>:state.error?<ErrorState onRetry={state.retry}/>:state.data?.items.length?<View style={styles.results}><Text accessibilityRole="header" style={styles.count}>{state.data.total} {state.data.total===1?'listing':'listings'}</Text><ListingList items={state.data.items}/></View>:<Empty message="No listings found" description={`There are no available listings for ${context}.`} action={<Action label="Refine filters" onPress={refine}/>}/>}</Screen>;
}
const styles=StyleSheet.create({results:{gap:spacing.md},count:{color:colors.primaryDark,fontWeight:'900',paddingHorizontal:spacing.sm}});
