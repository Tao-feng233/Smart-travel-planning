import pytest
from app import foods,schedule
from app.providers import DataError

def trip():
 return {'requirements':{'start_date':'2026-10-12','days':3},'catalog':{'f':{'id':'f','kind':'food','name':'海鲜店'}},'selected_spots':[]}

@pytest.mark.parametrize('departure',['2026-10-14 13:00','2026-10-14 14:30'])
def test_lunch_respects_return_preparation_and_full_duration(departure):
 w=trip();w['selected_return']={'departure':departure}
 with pytest.raises(DataError) as e:foods.select_meal(w,{'meal_date':'2026-10-14','meal_period':'lunch','food_id':'f'})
 assert e.value.context['view']=='food' and e.value.context['direction']=='return'
 assert not w.get('meal_choices')
 assert schedule.meal_start(w,'2026-10-14','lunch') is None

def test_late_lunch_is_flexible_when_full_meal_fits_after_arrival_buffer():
 w=trip();w['selected_transport']={'arrival':'2026-10-12 12:00'}
 foods.select_meal(w,{'meal_date':'2026-10-12','meal_period':'lunch','food_id':'f'})
 slot=next(x for x in schedule.build(w)['meal_slots'] if x['key']=='2026-10-12|lunch')
 assert slot['time']=='13:30' and slot['end']=='14:45'


def test_arrival_buffer_cannot_be_bypassed_by_manual_meal_choice():
 w=trip();w['selected_transport']={'arrival':'2026-10-12 13:00'}
 with pytest.raises(DataError):foods.select_meal(w,{'meal_date':'2026-10-12','meal_period':'lunch','food_id':'f'})


def test_later_transport_change_marks_existing_meal_without_moving_it():
 w=trip();foods.select_meal(w,{'meal_date':'2026-10-14','meal_period':'lunch','food_id':'f'})
 w['selected_return']={'departure':'2026-10-14 13:00'}
 c=next(x for x in schedule.build(w)['conflicts'] if x['code']=='meal_window')
 assert c['candidate_ids']==['f'] and c['meal_period']=='lunch'
 assert w['meal_choices']['2026-10-14|lunch']['food_id']=='f'


def test_self_arranged_meal_remains_available_when_transport_changes():
 w=trip();w['selected_return']={'departure':'2026-10-14 13:00'}
 assert '自行安排' in foods.select_meal(w,{'meal_date':'2026-10-14','meal_period':'lunch','meal_mode':'self'})
 assert not schedule.build(w)['conflicts']
