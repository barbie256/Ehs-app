import { useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet,Text,View,useWindowDimensions } from 'react-native';
import { api } from '@/api/client';
import { ListingList,MarketplaceGrid } from '@/components/catalogue';
import { Action,Empty,ErrorState,Header,Loading,Screen,SearchBar,SectionTitle } from '@/components/ui';
import { copy } from '@/content/copy'; import { useRequest } from '@/hooks/useRequest';
import { colors,layoutMode,radii,spacing,type } from '@/theme';
export default function Home(){
 const router=useRouter(); const {width}=useWindowDimensions(); const desktop=layoutMode(width)==='desktop'; const [q,setQ]=useState('');
 const markets=useRequest(s=>api.marketplaces(s),[]); const featured=useRequest(s=>api.listings({featured:true,perPage:6},s),[]);
 const latest=useRequest(s=>api.listings({orderBy:'newest',order:'desc',perPage:6},s),[]);
 const explore=()=>router.push({pathname:'/(tabs)/explore',params:{q:q.trim()}});
 return <Screen><Header/>
  <View style={[styles.hero,desktop&&styles.heroDesktop]}><View style={styles.heroGlow}/><View style={styles.heroCopy}><Text style={styles.eyebrow}>Discover across Africa</Text><Text style={[styles.heroText,desktop&&styles.heroTextDesktop]}>{copy.hero}</Text><Text style={styles.support}>{copy.heroSupport}</Text></View><View style={styles.discovery}><SearchBar value={q} onChangeText={setQ} onSubmit={explore}/><Action label="Explore catalogue" onPress={explore}/></View></View>
  <SectionTitle>Marketplaces</SectionTitle>{markets.loading?<Loading/>:markets.error?<ErrorState onRetry={markets.retry}/>:<MarketplaceGrid items={markets.data??[]} onPress={item=>router.push({pathname:'/results',params:{marketplace:item.code,title:item.name}})}/>}
  {featured.loading?<View><SectionTitle>Featured listings</SectionTitle><Loading/></View>:featured.error?<View><SectionTitle>Featured listings</SectionTitle><ErrorState onRetry={featured.retry}/></View>:featured.data?.items.length?<View style={styles.section}><SectionTitle>Featured listings</SectionTitle><ListingList items={featured.data.items}/></View>:null}
  <View style={styles.section}><SectionTitle>Latest listings</SectionTitle>{latest.loading?<Loading/>:latest.error?<ErrorState onRetry={latest.retry}/>:latest.data?.items.length?<ListingList items={latest.data.items}/>:<Empty/>}</View>
  <Text style={styles.location}>Discover trusted possibilities for better living across Africa.</Text>
 </Screen>;
}
const styles=StyleSheet.create({hero:{position:'relative',overflow:'hidden',padding:spacing.lg,backgroundColor:colors.primaryDark,borderRadius:radii.xl,gap:spacing.lg},heroDesktop:{paddingHorizontal:spacing.xxl,paddingVertical:spacing.xl,flexDirection:'row',alignItems:'center'},heroGlow:{position:'absolute',width:260,height:260,borderRadius:130,right:-80,top:-120,backgroundColor:'rgba(154,193,4,0.16)'},heroCopy:{flex:1,gap:spacing.sm},eyebrow:{color:colors.lime,fontSize:type.label,fontWeight:'900',letterSpacing:1.4,textTransform:'uppercase'},heroText:{fontSize:type.hero,fontWeight:'900',color:colors.white,lineHeight:40},heroTextDesktop:{fontSize:type.display,lineHeight:48},support:{color:'#DCE8E1',fontSize:type.body,lineHeight:24,maxWidth:620},discovery:{flex:1,gap:spacing.md,maxWidth:440},section:{gap:spacing.md},location:{color:colors.muted,textAlign:'center',paddingVertical:spacing.sm}});
