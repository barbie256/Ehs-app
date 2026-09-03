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
test('responsive layouts are deliberate',()=>{expect([layoutMode(390),listingColumns(390),marketplaceColumns(390)]).toEqual(['phone',1,1]);expect([layoutMode(768),listingColumns(768),marketplaceColumns(768)]).toEqual(['tablet',2,2]);expect([layoutMode(1280),listingColumns(1280),marketplaceColumns(1280)]).toEqual(['desktop',3,4]);});
test('desktop header navigation replaces mobile bottom tabs',()=>{const header=readFileSync(join(__dirname,'../components/ui.tsx'),'utf8');const tabs=readFileSync(join(__dirname,'../app/(tabs)/_layout.tsx'),'utf8');expect(header).toContain("desktop=layoutMode(width)==='desktop'");expect(header).toContain('desktop?<View');expect(tabs).toContain("display:desktop?'none':'flex'");});
