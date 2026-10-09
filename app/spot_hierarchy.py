"""Map-backed containment: selected scope containers do not add duplicate visits."""


def ancestors(catalog,cid):
    chain=[];seen={cid};node=cid
    while node in catalog:
        parent=catalog[node].get('parent_id')
        if not parent:return chain
        if parent in seen:return []  # Inconsistent cycles are not containment evidence.
        if parent in catalog and catalog[parent].get('kind')!='spot':return chain
        chain.append(parent);seen.add(parent);node=parent
    return chain


def state(w):
    cat=w.get('catalog',{});chosen=[cid for cid in dict.fromkeys(w.get('selected_spots',[])) if cat.get(cid,{}).get('kind')=='spot']
    chains={cid:ancestors(cat,cid) for cid in chosen}
    active=[cid for cid in chosen if not any(cid in chains[other] for other in chosen if other!=cid)]
    covered={cid:[leaf for leaf in active if cid in chains[leaf]] for cid in chosen if cid not in active}
    pins={cid:dict(pin) for cid,pin in w.get('visit_requests',{}).items()};issues=[]
    for leaf in active:
        constraints=[(cid,pins[cid]) for cid in reversed(chains[leaf]) if cid in covered and cid in pins]
        if leaf in pins:constraints.append((leaf,pins[leaf]))
        merged={};owners={}
        for cid,pin in constraints:
            for field in ('date','period'):
                value=pin.get(field)
                if value in (None,'','any'):continue
                if field in merged and merged[field]!=value:
                    other=owners[field]
                    issues.append({'code':'parent_child_schedule','level':'error','view':'spot','date':pin.get('date',''),
                        'candidate_ids':list(dict.fromkeys([other,cid])),
                        'message':cat[other]['name']+'与'+cat[cid]['name']+'属于同一景区范围，但指定'+('日期' if field=='date' else '时段')+'分别为'+str(merged[field])+'和'+str(value)+'。请调整父景区或子地点的指定安排，避免把同一范围重复排期。'})
                merged[field]=value;owners[field]=cid
        if merged:pins[leaf]={**pins.get(leaf,{}),**merged}
    order=[]
    for cid in w.get('visit_order',[]):
        for leaf in covered.get(cid,[cid]):
            if leaf in active and leaf not in order:order.append(leaf)
    return {'active_ids':active,'parent_coverage':covered,'visit_requests':pins,'visit_order':order,'issues':issues}


def candidates(catalog,items):
    ids={p['id'] for p in items}
    containers={parent for p in items for parent in ancestors(catalog,p['id']) if parent in ids}
    return [p for p in items if p['id'] not in containers]


def notes(w):
    cat=w.get('catalog',{})
    return [cat[parent]['name']+'作为已选景区范围保留，本次按'+ '、'.join(cat[cid]['name'] for cid in leaves)+'安排游玩，不再叠加父景区的独立游玩时长。'
            for parent,leaves in state(w)['parent_coverage'].items()]


def parent_facts(w):
    cat=w.get('catalog',{})
    return [{k:cat[cid].get(k) for k in ('id','name','location','description','recommendation','source')}
            for cid in state(w)['parent_coverage']]


def duplicate_plan(w,plan=None):
    plan=plan if plan is not None else w.get('plan') or {}
    parents=set(state(w)['parent_coverage'])
    return any(e.get('candidate_id') in parents and e.get('kind') in ('spot','spot_continue')
               for d in plan.get('days',[]) for e in d.get('events',[]))
