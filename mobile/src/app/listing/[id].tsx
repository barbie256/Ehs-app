import * as Linking from 'expo-linking';
import { useLocalSearchParams } from 'expo-router';
import { Alert,ScrollView,StyleSheet,Text,View,useWindowDimensions } from 'react-native';
import { api } from '@/api/client';
import { Location,Price,Rating,SaveButton } from '@/components/catalogue';
import { Action,Empty,ErrorState,Header,ImageFallback,Loading,Screen,SectionTitle } from '@/components/ui';
import { useRequest } from '@/hooks/useRequest';
import { colors,layoutMode,radii,spacing,type } from '@/theme';
import { isHttpsUrl,locationText } from '@/utils/format';

export function confirmExternal(url:string){if(!isHttpsUrl(url))return false;Alert.alert('Open external listing?','This link opens outside EHS Mall.',[{text:'Cancel',style:'cancel'},{text:'Continue',onPress:()=>void Linking.openURL(url)}]);return true;}

export default function Detail(){
 const {id}=useLocalSearchParams<{id:string}>();const {width}=useWindowDimensions();const desktop=layoutMode(width)==='desktop';
 const state=useRequest(signal=>api.listing(id,signal),[id]);
 if(state.loading)return <Screen><Header/><Loading label="Loading listing"/></Screen>;
 if(state.error)return <Screen><Header/><ErrorState onRetry={state.retry}/></Screen>;
 const item=state.data;if(!item)return <Screen><Header/><Empty message="This listing is unavailable" description="It may no longer be part of the public catalogue."/></Screen>;
 const lead=item.gallery[0]??item.primary_image;
 return <Screen><Header/>
  <View style={[styles.layout,desktop&&styles.layoutDesktop]}>
   <View style={styles.media}><ImageFallback url={lead?.url} alt={lead?.alt_text??item.title}/>{item.gallery.length>1?<ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.gallery}>{item.gallery.slice(1).map((image,index)=><View key={`${index}-${image.url}`} style={styles.thumbnail}><ImageFallback url={image.url} alt={image.alt_text}/></View>)}</ScrollView>:null}</View>
   <View style={styles.summary}><Text style={styles.eyebrow}>{item.marketplace.name} · {item.primary_category.name}</Text><Text accessibilityRole="header" style={styles.title}>{item.title}</Text>{item.tagline?<Text style={styles.tagline}>{item.tagline}</Text>:null}<View style={styles.location}><Location name={locationText(item.location_hierarchy)}/></View><View style={styles.pricePanel}><Price amount={item.price} currency={item.currency}/><Text style={styles.pricing}>{item.pricing_type.replaceAll('_',' ')}</Text><Rating rating={item.rating} count={item.rating_count}/></View><SaveButton id={item.id}/>{isHttpsUrl(item.source_url)?<View style={styles.secondary}><Action label="View original EHS listing" onPress={()=>confirmExternal(item.source_url!)}/></View>:null}</View>
  </View>
  <View style={styles.details}><View style={styles.detailSection}><SectionTitle>About this listing</SectionTitle><Text style={styles.body}>{item.description}</Text></View><View style={styles.detailSection}><SectionTitle>Categories</SectionTitle><Text style={styles.body}>{item.categories.map(category=>category.name).join(' · ')}</Text></View></View>
 </Screen>;
}

const styles=StyleSheet.create({layout:{gap:spacing.lg},layoutDesktop:{flexDirection:'row',alignItems:'flex-start'},media:{flex:1.35,gap:spacing.sm,overflow:'hidden',borderRadius:radii.lg},summary:{flex:1,backgroundColor:colors.surface,borderRadius:radii.lg,borderWidth:1,borderColor:colors.border,padding:spacing.xl,gap:spacing.md},eyebrow:{color:colors.primary,fontSize:type.label,fontWeight:'900',textTransform:'uppercase',letterSpacing:.8},title:{fontSize:type.displaySmall,lineHeight:38,fontWeight:'900',color:colors.primaryDark},tagline:{fontSize:type.heading,lineHeight:28,color:colors.text},location:{paddingVertical:spacing.sm,borderTopWidth:1,borderBottomWidth:1,borderColor:colors.border},pricePanel:{backgroundColor:colors.limeSoft,borderRadius:radii.md,padding:spacing.md,gap:spacing.xs},pricing:{color:colors.muted,textTransform:'capitalize',fontSize:type.small},secondary:{opacity:.82},gallery:{gap:spacing.sm},thumbnail:{width:180,borderRadius:radii.md,overflow:'hidden'},details:{gap:spacing.lg,flexDirection:'row',flexWrap:'wrap'},detailSection:{flex:1,minWidth:280,backgroundColor:colors.surfaceWarm,borderRadius:radii.lg,padding:spacing.lg,gap:spacing.sm},body:{fontSize:type.body,lineHeight:26,color:colors.text}});
