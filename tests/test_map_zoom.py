import pytest
from app import maps
from app.providers import DataError

def test_zoom_changes_real_map_level_without_moving_center():
 ps=[{'location':'120.14,30.25'},{'location':'120.1,30.23'}]
 auto=maps.params(ps,True);closer=maps.params(ps,True,auto['zoom']+1)
 assert closer['zoom']==auto['zoom']+1
 assert auto['location']==closer['location'] and auto['paths']==closer['paths']
 assert 'key' not in closer and closer['scale']==1

def test_fit_level_covers_wide_area_and_zoom_is_bounded():
 ps=[{'location':'120,30'},{'location':'121,31'}]
 assert maps.params(ps)['zoom']<maps.params([ps[0]])['zoom']
 for level in (0,18):
  with pytest.raises(DataError):maps.params(ps,zoom=level)

def test_marker_count_obeys_static_api_limit():
 ps=[{'location':f'{120+i*.001},30'} for i in range(15)]
 assert len(maps.params(ps)['markers'].split('|'))==10

def test_pointer_zoom_center_is_forwarded_and_validated():
 ps=[{'location':'120.14,30.25'}]
 assert maps.params(ps,zoom=16,center=(120.15,30.26))['location']=='120.15,30.26'
 for center in ((float('nan'),30),(180.01,30),(120,86),(120,)):
  with pytest.raises(DataError):maps.params(ps,zoom=16,center=center)
