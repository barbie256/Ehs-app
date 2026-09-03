// @ts-expect-error Node built-ins are supplied by the Jest runtime only.
import { createHash } from 'crypto';
// @ts-expect-error Node built-ins are supplied by the Jest runtime only.
import { readFileSync } from 'fs';
// @ts-expect-error Node built-ins are supplied by the Jest runtime only.
import { join } from 'path';
import { layoutMode,listingColumns,marketplaceColumns } from '@/theme';
declare const __dirname:string;
test('official source logo remains byte-for-byte preserved',()=>{const source=readFileSync(join(__dirname,'../../assets/branding/ehs-mall-logo.png'));expect(createHash('sha256').update(source).digest('hex')).toBe('c7927d6e6a5fcd362343122edd9d62cdfc1c16829a8b9221ec32802a45d1f8f7');});
test('cropped brand mark has deterministic dimensions',()=>{const png=readFileSync(join(__dirname,'../../assets/branding/ehs-mall-logo-mark-cropped.png'));expect([png.readUInt32BE(16),png.readUInt32BE(20)]).toEqual([889,894]);});
test('favicon is a deterministic square PNG configured for Expo web',()=>{const favicon=readFileSync(join(__dirname,'../../assets/branding/ehs-mall-favicon.png'));expect(favicon.subarray(1,4).toString()).toBe('PNG');expect([favicon.readUInt32BE(16),favicon.readUInt32BE(20)]).toEqual([894,894]);const config=JSON.parse(readFileSync(join(__dirname,'../../app.json'),'utf8'));expect(config.expo.web.favicon).toBe('./assets/branding/ehs-mall-favicon.png');});
test('responsive layouts are deliberate',()=>{expect([layoutMode(390),listingColumns(390),marketplaceColumns(390)]).toEqual(['phone',1,1]);expect([layoutMode(768),listingColumns(768),marketplaceColumns(768)]).toEqual(['tablet',2,2]);expect([layoutMode(1280),listingColumns(1280),marketplaceColumns(1280)]).toEqual(['desktop',3,4]);});
test('desktop header navigation replaces mobile bottom tabs',()=>{const header=readFileSync(join(__dirname,'../components/ui.tsx'),'utf8');const tabs=readFileSync(join(__dirname,'../app/(tabs)/_layout.tsx'),'utf8');expect(header).toContain("desktop=layoutMode(width)==='desktop'");expect(header).toContain('desktop?<View');expect(tabs).toContain("display:desktop?'none':'flex'");});
test('customer copy uses the approved tagline and omits technical placeholder language',()=>{const mobileRoot=join(__dirname,'..');const files=['content/copy.ts','app/(tabs)/index.tsx','components/ui.tsx'].map(file=>readFileSync(join(mobileRoot,file),'utf8')).join('\n');expect(files).toContain('A click away to better living');expect(files).not.toContain('Africa-ready public catalogue');expect(files).not.toContain('location defaults');});
