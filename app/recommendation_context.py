"""Optional preference discovery and dated facts for recommendation reasoning."""
from . import visits


PREFERENCE_QUESTION=('为了更精细地推荐景点，请提供旅行偏好，例如海滨、人文、自然风光、亲子游，或说明希望少走路等要求。'
    '\n如果暂无偏好，可点击“暂无偏好，查看代表景点”，也可以直接在对话中说明。默认参考城市代表景点资料与地图评分，不代表实时热度排行。')


def needs_preferences(w,args):
    r=w['requirements'];state=w.get('spot_preference') or {}
    if not r.get('city'):return False
    if r.get('preferences'):
        w['spot_preference']={'city':r['city'],'status':'custom'}
        return False
    if args.get('preference_mode')=='default':
        w['spot_preference']={'city':r['city'],'status':'default'}
        return False
    # Explicit named/topic queries and authorized delegation already provide a direction.
    if args.get('keywords') or args.get('prefer_known') or w.get('auto_selection_run') or w.get('pending_auto_selection'):
        w['spot_preference']={'city':r['city'],'status':'direct'}
        return False
    if state.get('city')==r['city'] and state.get('status')=='default':return False
    if (w.get('spot_search') or {}).get('city')==r['city']:return False
    return True


def ask(w):
    w['spot_preference']={'city':w['requirements']['city'],'status':'awaiting'}
    return PREFERENCE_QUESTION


def context(w):
    r=w['requirements'];dates=visits.dates(w);weather=w.get('weather') or {}
    identity=w.get('weather_for')
    applicable=identity==[r.get('city'),r.get('start_date'),r.get('days')]
    rows=[d for d in weather.get('days',[]) if d.get('date') in dates] if applicable else []
    covered={d['date'] for d in rows}
    return {'party':{k:r.get(k) for k in ('adults','children','child_ages','companion_notes','hard_constraints','pace')},
        'weather':{'days':rows,'source':weather.get('source') if rows else None,
                   'uncovered_dates':[d for d in dates if d not in covered],
                   'status':'partial' if rows and len(covered)<len(dates) else 'available' if rows else 'unknown',
                   'note':w.get('weather_note')},
        'ranking_basis':'用户偏好与已知条件优先；无偏好时参考城市代表景点资料、地图评分和位置。无实时热度数据。'}
