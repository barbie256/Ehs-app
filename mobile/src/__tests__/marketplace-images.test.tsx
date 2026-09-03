// @ts-expect-error Node built-ins are supplied by the Jest runtime only.
import { createHash } from 'crypto';
// @ts-expect-error Node built-ins are supplied by the Jest runtime only.
import { readFileSync } from 'fs';
// @ts-expect-error Node built-ins are supplied by the Jest runtime only.
import { join } from 'path';
import { fireEvent,render } from '@testing-library/react-native';
import { MarketplaceCard } from '@/components/catalogue';
import { marketplaceFallback,marketplaceImage,marketplaceImages,marketplaceTextOverlayOpacity } from '@/content/marketplaceImages';
import { listingColumns,marketplaceColumns } from '@/theme';

declare const __dirname:string;
type Metadata={file:string;format:string;width:number;height:number;bytes:number;sha256:string};
const directory=join(__dirname,'../../assets/marketplaces');
const metadata:Record<string,Metadata>=JSON.parse(readFileSync(join(directory,'metadata.json'),'utf8'));
function jpegDimensions(bytes:Uint8Array):[number,number] {
 const word=(offset:number)=>((bytes[offset]??0)<<8)|(bytes[offset+1]??0);
 if(word(0)!==0xffd8)throw new Error('Not JPEG');
 for(let offset=2;offset+8<bytes.length;){
  if(bytes[offset]!==0xff)throw new Error('Invalid JPEG marker');
  const marker=bytes[offset+1];const length=word(offset+2);
  if(marker===0xc0||marker===0xc1||marker===0xc2)return [word(offset+7),word(offset+5)];
  if(length<2)throw new Error('Invalid JPEG segment');
  offset+=length+2;
 }
 throw new Error('Missing JPEG dimensions');
}
test('exactly four canonical codes have unique bundled photographs',()=>{
 expect(Object.keys(marketplaceImages)).toEqual(['property','construction','home_interior','professional_services']);
 expect(Object.keys(metadata)).toEqual(Object.keys(marketplaceImages));
 expect(new Set(Object.values(metadata).map(item=>item.file)).size).toBe(4);
 for(const code of Object.keys(metadata))expect(marketplaceImage(code)).toBe(marketplaceImages[code as keyof typeof marketplaceImages]);
});
test.each(Object.entries(metadata))('%s approved JPEG metadata and bytes remain frozen',(_code,item)=>{
 const bytes=readFileSync(join(directory,item.file));
 expect(item.format).toBe('JPEG');expect(jpegDimensions(bytes)).toEqual([item.width,item.height]);
 expect(bytes.length).toBe(item.bytes);expect(bytes.length).toBeLessThan(5*1024*1024);
 expect(createHash('sha256').update(bytes).digest('hex')).toBe(item.sha256);
});
test('unknown marketplace uses only the branded fallback and retains its real count',()=>{
 expect(marketplaceImage('unknown')).toBeUndefined();expect(marketplaceImage('toString')).toBeUndefined();
 const press=jest.fn();const view=render(<MarketplaceCard item={{code:'unknown',name:'Other marketplace',listing_count:7}} onPress={press}/>);
 expect(view.getByTestId('marketplace-image').props.source).toEqual(marketplaceFallback);
 expect(view.getByTestId('marketplace-image').props.resizeMode).toBe('contain');
 fireEvent.press(view.getByRole('button',{name:'Browse Other marketplace, 7 listings'}));expect(press).toHaveBeenCalledTimes(1);
 expect(view.getByText('7 listings')).toBeTruthy();
});
test('canonical card covers the image and announces the API-provided name and count',()=>{
 const view=render(<MarketplaceCard item={{code:'construction',name:'Construction',listing_count:23}} onPress={()=>{}}/>);
 expect(view.getByTestId('marketplace-image').props.source).toEqual(marketplaceImages.construction);
 expect(view.getByTestId('marketplace-image').props.resizeMode).toBe('cover');
 expect(view.getByRole('button',{name:'Browse Construction, 23 listings'})).toBeTruthy();
 expect(view.getByText('23 listings')).toBeTruthy();
});
test('white caption contrast exceeds AA even over an entirely white photograph',()=>{
 const channel=1-marketplaceTextOverlayOpacity;
 const luminance=channel<=.04045?channel/12.92:Math.pow((channel+.055)/1.055,2.4);
 expect(1.05/(luminance+.05)).toBeGreaterThanOrEqual(4.5);
});
test('marketplace assets cannot introduce a runtime website request',()=>{
 const source=readFileSync(join(__dirname,'../content/marketplaceImages.ts'),'utf8');
 const card=readFileSync(join(__dirname,'../components/catalogue.tsx'),'utf8');
 expect(source).not.toMatch(/https?:\/\/|ehsmall\.com|\bfetch\s*\(/i);
 expect(card).not.toMatch(/https?:\/\/|ehsmall\.com/);
 expect((source.match(/assets\/marketplaces\/[^']+\.jpg/g)??[])).toHaveLength(4);
});
test('photographic grids preserve phone, tablet, desktop and listing column boundaries',()=>{
 expect([390,430,768,1280].map(marketplaceColumns)).toEqual([1,2,2,4]);
 expect([390,768,1280].map(listingColumns)).toEqual([1,2,3]);
});
