from app.travel import price_hints
from datetime import date, timedelta


def trip():
    # 出游日期用相对今天生成：硬编码日期过期后 ticket_date 抛错，门票快照会被判为不匹配而全部丢弃。
    return {'requirements':{'city':'青岛','start_date':(date.today()+timedelta(days=1)).isoformat(),'days':3},'tickets':{}}


def test_missing_and_zero_map_cost_do_not_claim_free_admission():
    w=trip()
    assert price_hints.hint(w,{'id':'s','name':'未知景区','kind':'spot'})['basis']=='unknown'
    h=price_hints.hint(w,{'id':'s','name':'未知景区','kind':'spot','cost':'0'})
    assert h['basis']=='map_reference' and '免费' not in h['label']


def test_food_cost_is_reference_and_bad_values_are_unknown():
    w=trip()
    assert price_hints.hint(w,{'kind':'food','cost':'94'})['label']=='参考人均 ¥94'
    for value in ('NaN','-3','未知',True):
        assert price_hints.hint(w,{'kind':'food','cost':value})['basis']=='unknown'


def test_ticket_hint_ignores_child_addon_and_old_date_prices():
    w=trip();p={'id':'s','name':'收费景区','kind':'spot'}
    # 快照 requested_date 必须等于游玩日期才采信；stale 是"与游玩日期不符的旧快照"，用来验证被忽略。
    visit=w['requirements']['start_date']
    stale=(date.fromisoformat(visit)+timedelta(days=1)).isoformat()
    w['tickets']['s']={'requested_date':visit,'items':[
        {'startPrice':20,'product_group':'addon','date_status':'in_sales_window','personTypeName':'成人'},
        {'startPrice':40,'product_group':'admission','date_status':'in_sales_window','personTypeName':'儿童'},
        {'startPrice':169,'product_group':'admission','date_status':'in_sales_window','personTypeName':'成人'}]}
    assert price_hints.hint(w,p)['label']=='门票起价 ¥169'
    w['tickets']['s']['requested_date']=stale
    assert price_hints.hint(w,p)['basis']=='unknown'


def test_official_free_policy_has_exact_city_name_and_recheck_window(monkeypatch):
    w=trip();p={'id':'s','name':'青岛市博物馆','kind':'spot'}
    h=price_hints.hint(w,p)
    assert h['basis']=='official_free_admission' and h['source']['url'].endswith('/service/free')
    assert price_hints.hint(w,{**p,'name':'青岛市博物馆·付费讲解'})['basis']=='unknown'
    w['requirements']['city']='杭州'
    assert price_hints.hint(w,p)['basis']=='unknown'
    w['requirements'].update(city='青岛',start_date='2027-10-12')
    assert price_hints.hint(w,p)['basis']=='unknown'
