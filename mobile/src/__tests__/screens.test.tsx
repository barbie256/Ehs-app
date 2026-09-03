import { Alert } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent,render,waitFor } from '@testing-library/react-native';
import { api } from '@/api/client';
import Home from '@/app/(tabs)/index';
import Explore from '@/app/(tabs)/explore';
import Saved from '@/app/(tabs)/saved';
import Detail,{confirmExternal} from '@/app/listing/[id]';
import Results from '@/app/results';
import { SavedProvider } from '@/state/SavedContext';
import { listing,page } from '@/test/fixtures';

jest.mock('@/api/client',()=>({api:{marketplaces:jest.fn(),categories:jest.fn(),locations:jest.fn(),listings:jest.fn(),listing:jest.fn()}}));
const mocked=api as jest.Mocked<typeof api>;
const markets=[{code:'property',name:'Property',listing_count:1},{code:'construction',name:'Construction',listing_count:2},{code:'home_interior',name:'Home & Interior',listing_count:0},{code:'professional_services',name:'Professional Services',listing_count:0}];

beforeEach(()=>{jest.clearAllMocks();mocked.marketplaces.mockResolvedValue(markets);mocked.categories.mockResolvedValue([]);mocked.locations.mockResolvedValue([]);mocked.listings.mockResolvedValue(page);mocked.listing.mockResolvedValue(listing);});

test('home presents the approved tagline and polished success sections',async()=>{const view=render(<SavedProvider><Home/></SavedProvider>);expect(view.getAllByText('Loading catalogue').length).toBeGreaterThan(0);await waitFor(()=>expect(view.getAllByText('A click away to better living').length).toBeGreaterThan(0));expect(view.queryByText('Africa-ready public catalogue')).toBeNull();expect(view.getByRole('button',{name:'Explore catalogue'})).toBeTruthy();expect(view.getByText('Featured listings')).toBeTruthy();expect(view.getByText('Latest listings')).toBeTruthy();});

test('home exposes retry after controlled error',async()=>{mocked.marketplaces.mockRejectedValueOnce(new Error('offline'));const view=render(<SavedProvider><Home/></SavedProvider>);await waitFor(()=>expect(view.getByRole('button',{name:'Try again'})).toBeTruthy());});

test('home hides empty featured and preserves latest empty state',async()=>{mocked.listings.mockResolvedValue({...page,items:[],total:0});const view=render(<SavedProvider><Home/></SavedProvider>);await waitFor(()=>expect(view.getByText('Latest listings')).toBeTruthy());expect(view.queryByText('Featured listings')).toBeNull();expect(view.getByText('No listings match these filters.')).toBeTruthy();});

test('explore organizes filters and presents a contextual empty state',async()=>{mocked.listings.mockResolvedValue({...page,items:[],total:0});const view=render(<SavedProvider><Explore/></SavedProvider>);fireEvent.changeText(view.getByLabelText('Search catalogue'),'synthetic');fireEvent(view.getByLabelText('Search catalogue'),'submitEditing');await waitFor(()=>expect(mocked.listings).toHaveBeenCalled());expect(view.getByLabelText('Catalogue filters')).toBeTruthy();expect(view.getByText('Marketplace')).toBeTruthy();expect(view.getByText('Category')).toBeTruthy();expect(view.getByText('Location')).toBeTruthy();expect(view.getByText('Sort')).toBeTruthy();expect(view.getByText('No listings found')).toBeTruthy();});

test('results presents count, context and a refine action',async()=>{const view=render(<SavedProvider><Results/></SavedProvider>);await waitFor(()=>expect(view.getByText('1 listing')).toBeTruthy());expect(view.getByText('Showing All marketplaces')).toBeTruthy();expect(view.getByRole('button',{name:'Refine filters'})).toBeTruthy();});

test('detail renders structured public fields without contact promises',async()=>{const view=render(<SavedProvider><Detail/></SavedProvider>);await waitFor(()=>expect(view.getByText('Synthetic Building')).toBeTruthy());expect(view.getByText('Construction · Cement')).toBeTruthy();expect(view.getByText(/Africa › Uganda › Kampala/)).toBeTruthy();expect(view.queryByText(/seller contact/i)).toBeNull();expect(view.queryByText(/contact seller/i)).toBeNull();fireEvent.press(view.getByRole('button',{name:'Save listing'}));await waitFor(()=>expect(view.getByRole('button',{name:'Remove saved listing'})).toBeTruthy());});

test('detail renders controlled unavailable error',async()=>{mocked.listing.mockRejectedValueOnce(new Error('unavailable'));const view=render(<SavedProvider><Detail/></SavedProvider>);await waitFor(()=>expect(view.getByRole('button',{name:'Try again'})).toBeTruthy());});

test('saved screen presents a deliberate branded empty state',async()=>{await AsyncStorage.clear();const view=render(<SavedProvider><Saved/></SavedProvider>);await waitFor(()=>expect(view.getByText('Your shortlist is ready when you are')).toBeTruthy());expect(view.getByText('Save listings as you browse, then return here to compare them.')).toBeTruthy();expect(view.getByRole('button',{name:'Explore listings'})).toBeTruthy();});

test('external links require HTTPS and confirmation',()=>{const alert=jest.spyOn(Alert,'alert').mockImplementation(()=>{});expect(confirmExternal('http://example.invalid')).toBe(false);expect(confirmExternal('https://example.invalid')).toBe(true);expect(alert).toHaveBeenCalledWith('Open external listing?',expect.any(String),expect.any(Array));});
