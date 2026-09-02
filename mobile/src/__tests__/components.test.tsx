import { fireEvent,render } from '@testing-library/react-native'; import { Price,Rating } from '@/components/catalogue'; import { Action,ImageFallback,SearchBar } from '@/components/ui';
describe('accessible controls and display',()=>{
 test('labels primary controls and search',()=>{const press=jest.fn();const view=render(<><SearchBar value="" onChangeText={()=>{}} onSubmit={press}/><Action label="Try again" onPress={press}/></>);expect(view.getByLabelText('Search catalogue')).toBeTruthy();fireEvent.press(view.getByRole('button',{name:'Try again'}));expect(press).toHaveBeenCalled();});
 test('shows price-on-request and accessible rating',()=>{const view=render(<><Price amount={null} currency={null}/><Rating rating={null} count={0}/></>);expect(view.getByText('Price on request')).toBeTruthy();expect(view.getByLabelText('No ratings yet')).toBeTruthy();});
 test('uses an accessible image fallback',()=>{expect(render(<ImageFallback alt="Synthetic"/>).getByLabelText('Image unavailable')).toBeTruthy();});
});
