import { useLocalSearchParams } from 'expo-router';
import { useMemo,useState } from 'react';
import { StyleSheet,Text,View,useWindowDimensions } from 'react-native';
import { api } from '@/api/client';
import type { ListingFilters,ListingOrder,SortDirection } from '@/api/types';
import { ListingList } from '@/components/catalogue';
import { Action,Chip,Empty,ErrorState,Header,Loading,PageIntro,Screen,SearchBar } from '@/components/ui';
import { useRequest } from '@/hooks/useRequest';
import { colors,layoutMode,radii,spacing,type } from '@/theme';

const marketplaceOptions=[['property','Property'],['construction','Construction'],['home_interior','Home & Interior'],['professional_services','Professional Services']] as const;
const titleCase=(value:string)=>value.replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase());

export default function Explore(){
 const initial=useLocalSearchParams<{q?:string;marketplace?:string;category?:string;location?:string}>();const {width}=useWindowDimensions();const desktop=layoutMode(width)==='desktop';
 const [draft,setDraft]=useState(initial.q??'');const [filters,setFilters]=useState<ListingFilters>({q:initial.q,marketplace:initial.marketplace,category:initial.category,location:initial.location,orderBy:'newest',order:'desc'});
 const key=JSON.stringify(filters);const state=useRequest(signal=>api.listings(filters,signal),[key]);
 const categories=useRequest(signal=>api.categories(filters.marketplace,signal),[filters.marketplace]);const locations=useRequest(signal=>api.locations(signal),[]);
 const update=(next:Partial<ListingFilters>)=>setFilters(current=>({...current,...next,page:1}));
 const activeCount=useMemo(()=>[filters.q,filters.marketplace,filters.category,filters.location,filters.featured].filter(Boolean).length,[filters]);
 const locationOptions=locations.data?.flatMap(root=>[root,...root.children.flatMap(country=>[country,...country.children])])??[];
 const clear=()=>{setDraft('');setFilters({orderBy:'newest',order:'desc'});};
 const filterPanel=<View accessibilityLabel="Catalogue filters" style={styles.filters}>
  <View style={styles.filterHeading}><Text style={styles.panelTitle}>Filters</Text><Text style={styles.filterCount}>{activeCount} active</Text></View>
  <View style={styles.group}><Text style={styles.label}>Search</Text><SearchBar value={draft} onChangeText={setDraft} onSubmit={()=>update({q:draft.trim()||undefined})}/></View>
  <View style={styles.group}><Text style={styles.label}>Marketplace</Text><View style={styles.chips}>{marketplaceOptions.map(([code,label])=><Chip key={code} label={label} active={filters.marketplace===code} onPress={()=>update({marketplace:filters.marketplace===code?undefined:code,category:undefined})}/>)}</View></View>
  <View style={styles.group}><Text style={styles.label}>Category</Text>{filters.marketplace?<View style={styles.chips}>{categories.data?.slice(0,12).map(item=><Chip key={`${item.marketplace}-${item.code}`} label={item.name} active={filters.category===item.code} onPress={()=>update({category:filters.category===item.code?undefined:item.code})}/>)}</View>:<Text style={styles.hint}>Choose a marketplace to see its categories.</Text>}</View>
  <View style={styles.group}><Text style={styles.label}>Location</Text><View style={styles.chips}>{locationOptions.map(item=><Chip key={item.code} label={item.name} active={filters.location===item.code} onPress={()=>update({location:filters.location===item.code?undefined:item.code})}/>)}</View></View>
  <View style={[styles.group,styles.sortGroup]}><Text style={styles.label}>Sort</Text><View style={styles.chips}>{(['newest','title','rating'] as ListingOrder[]).map(value=><Chip key={value} label={titleCase(value)} active={filters.orderBy===value} onPress={()=>update({orderBy:value})}/>)}<Chip label={filters.order==='asc'?'Ascending':'Descending'} active={filters.order==='asc'} onPress={()=>update({order:(filters.order==='asc'?'desc':'asc') as SortDirection})}/><Chip label="Featured" active={filters.featured===true} onPress={()=>update({featured:filters.featured?undefined:true})}/></View></View>
  {activeCount?<View style={styles.clear}><Action label="Clear filters" onPress={clear}/></View>:null}
 </View>;
 return <Screen><Header/><PageIntro eyebrow="Explore" title="Find what fits your next move" description="Browse public listings by marketplace, category and location."/>
  <View style={[styles.layout,desktop&&styles.layoutDesktop]}>{filterPanel}<View accessibilityLabel="Catalogue results" style={styles.results}>
   {state.loading?<Loading label="Finding listings"/>:state.error?<ErrorState onRetry={state.retry}/>:state.data?.items.length?<><View style={styles.resultsHeading}><Text accessibilityRole="header" style={styles.resultsTitle}>{state.data.total} {state.data.total===1?'result':'results'}</Text><Text style={styles.hint}>{activeCount?`${activeCount} active ${activeCount===1?'filter':'filters'}`:'Showing the full catalogue'}</Text></View><ListingList items={state.data.items}/>{state.data.has_next?<Action label="Load more results" onPress={()=>setFilters(current=>({...current,page:(current.page??1)+1}))}/>:null}</>:<Empty message="No listings found" description="Try removing a filter or searching for something broader." action={activeCount?<Action label="Clear filters" onPress={clear}/>:undefined}/>}</View></View>
 </Screen>;
}

const styles=StyleSheet.create({layout:{gap:spacing.lg},layoutDesktop:{flexDirection:'row',alignItems:'flex-start'},filters:{backgroundColor:colors.surface,borderWidth:1,borderColor:colors.border,borderRadius:radii.lg,padding:spacing.lg,gap:spacing.lg,flexBasis:340},results:{flex:1,minWidth:0,gap:spacing.md},filterHeading:{flexDirection:'row',justifyContent:'space-between',alignItems:'center'},panelTitle:{fontSize:type.heading,fontWeight:'900',color:colors.primaryDark},filterCount:{color:colors.primary,fontWeight:'800'},group:{gap:spacing.sm},sortGroup:{borderTopWidth:1,borderTopColor:colors.border,paddingTop:spacing.md},label:{fontSize:type.small,fontWeight:'900',color:colors.text},hint:{color:colors.muted,lineHeight:20},chips:{flexDirection:'row',flexWrap:'wrap',gap:spacing.sm},clear:{alignItems:'flex-start'},resultsHeading:{paddingHorizontal:spacing.sm,gap:spacing.xs},resultsTitle:{fontSize:type.title,fontWeight:'900',color:colors.primaryDark}});
