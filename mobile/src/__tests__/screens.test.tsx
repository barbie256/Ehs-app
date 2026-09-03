import { Alert } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent,render,waitFor } from '@testing-library/react-native';
import { api } from '@/api/client';
import Home from '@/app/(tabs)/index';
import Explore from '@/app/(tabs)/explore';
import Saved from '@/app/(tabs)/saved';
import Detail,{confirmExternal} from '@/app/listing/[id]';
import { SavedProvider } from '@/state/SavedContext';
import { listing,page } from '@/test/fixtures';

jest.mock('@/api/client',()=>({api:{marketplaces:jest.fn(),categories:jest.fn(),locations:jest.fn(),listings:jest.fn(),listing:jest.fn()}}));
const mocked=api as jest.Mocked<typeof api>;
const markets=[{code:'property',name:'Property',listing_count:1},{code:'construction',name:'Construction',listing_count:2},{code:'home_interior',name:'Home & Interior',listing_count:0},{code:'professional_services',name:'Professional Services',listing_count:0}];

beforeEach(()=>{jest.clearAllMocks();mocked.marketplaces.mockResolvedValue(markets);mocked.categories.mockResolvedValue([]);mocked.locations.mockResolvedValue([]);mocked.listings.mockResolvedValue(page);mocked.listing.mockResolvedValue(listing);});

test('home renders loading then polished success sections',async()=>{const view=render(<SavedProvider><Home/></SavedProvider>);expect(view.getAllByText('Loading catalogue').length).toBeGreaterThan(0);await waitFor(()=>expect(view.getByText('Africa’s marketplace for building, property and better living.')).toBeTruthy());expect(view.getByRole('button',{name:'Explore catalogue'})).toBeTruthy();expect(view.getByText('Featured listings')).toBeTruthy();expect(view.getByText('Latest listings')).toBeTruthy();});

test('home exposes retry after controlled error',async()=>{mocked.marketplaces.mockRejectedValueOnce(new Error('offline'));const view=render(<SavedProvider><Home/></SavedProvider>);await waitFor(()=>expect(view.getByRole('button',{name:'Try again'})).toBeTruthy());});

test('home hides empty featured and preserves latest empty state',async()=>{mocked.listings.mockResolvedValue({...page,items:[],total:0});const view=render(<SavedProvider><Home/></SavedProvider>);await waitFor(()=>expect(view.getByText('Latest listings')).toBeTruthy());expect(view.queryByText('Featured listings')).toBeNull();expect(view.getByText('No listings match these filters.')).toBeTruthy();});

test('explore submits search and exposes filters and empty state',async()=>{mocked.listings.mockResolvedValue({...page,items:[],total:0});const view=render(<SavedProvider><Explore/></SavedProvider>);fireEvent.changeText(view.getByLabelText('Search catalogue'),'synthetic');fireEvent(view.getByLabelText('Search catalogue'),'submitEditing');await waitFor(()=>expect(mocked.listings).toHaveBeenCalled());expect(view.getByText('Marketplace')).toBeTruthy();expect(view.getByText('Category')).toBeTruthy();expect(view.getByText('Location')).toBeTruthy();});

test('detail renders public fields without a contact action',async()=>{const view=render(<SavedProvider><Detail/></SavedProvider>);await waitFor(()=>expect(view.getByText('Synthetic Building')).toBeTruthy());expect(view.getByText('Seller contact options will be available in a later release.')).toBeTruthy();expect(view.queryByText(/contact seller/i)).toBeNull();fireEvent.press(view.getByRole('button',{name:'Save listing'}));await waitFor(()=>expect(view.getByRole('button',{name:'Remove saved listing'})).toBeTruthy());});

test('detail renders controlled unavailable error',async()=>{mocked.listing.mockRejectedValueOnce(new Error('unavailable'));const view=render(<SavedProvider><Detail/></SavedProvider>);await waitFor(()=>expect(view.getByRole('button',{name:'Try again'})).toBeTruthy());});

test('saved screen restores an empty identifier set safely',async()=>{await AsyncStorage.clear();const view=render(<SavedProvider><Saved/></SavedProvider>);await waitFor(()=>expect(view.getByText('Save listings to find them here later.')).toBeTruthy());expect(view.getByRole('link',{name:'Explore listings'})).toBeTruthy();});

test('external links require HTTPS and confirmation',()=>{const alert=jest.spyOn(Alert,'alert').mockImplementation(()=>{});expect(confirmExternal('http://example.invalid')).toBe(false);expect(confirmExternal('https://example.invalid')).toBe(true);expect(alert).toHaveBeenCalledWith('Open external listing?',expect.any(String),expect.any(Array));});
