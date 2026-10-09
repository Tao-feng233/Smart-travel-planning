# 识途旅游规划

## Containment and visible transport legs (2026-10-09)

`spot_hierarchy` follows explicit map `parent_id` chains, with cycle/unknown-type guards. Recommendation groups use the highest known parent so a nested child no longer appears both inside one group and as another group header. Parent scope cards are labelled separately. Candidate ranking suppresses broad containers when their concrete descendants are in the same batch; names alone remain only an unverified association. Selected parent/child IDs are preserved. Actual sightseeing analysis/preview/proposals/revision checks use the selected concrete descendants, attach `parent_coverage` and retain area-level context rather than adding another full parent duration. Explicit ancestor date/period constraints propagate; contradictory pins identify both entries for repair. Old double-counted books are treated as needing regeneration, without rewriting user records.

Formal planning already queried local roads. Its shared scheduler now also produces a route-aware time-axis preview, without another proposal/review model call. Relevant selection/completion jobs refresh the preview with bounded road queries; changed input, entrance, city code or analysis invalidates it, and ready results are reused for 15 minutes. Timeline rows now include hotel/spot/meal/spot transport segments, mode, predicted road minutes, separate buffer, source time and a clickable explanation. Unknown roads and pending schedules remain labelled, not declared impassable. Preview state is not a published book or permission to change choices.

`transport_links` can uniquely match selected train stations or airport main POIs to map coordinates, then query their hotel links. Timetable moments remain from user-selected supplier candidates. Known road time plus suggested exit/checkout/boarding buffers can extend the conservative arrival/return windows; unresolved names/coordinates retain the prior labelled estimate. Airport primary coordinates do not confirm a terminal or entrance. Cross-midnight transfers are flagged instead of fabricated inside a single calendar day. Parent-scope validation and road timing share the same final planner; map/provider responses in new regression cases are fixtures. Verification: 307 backend tests; browser hierarchy/card/transport-detail, assistance and optional-room checks.

## Leisure pacing and whole-trip recommendation batches (2026-10-09)

`pacing` provides midday rest separate from lunch and inter-visit leisure breaks. Initial defaults are 60 and 30 minutes; sightseeing analysis can return checked `day_pacing` suggestions per tour date (rest 30–120, breaks 15–60) with reasons, based on explicit party/mobility needs, applicable weather and the visit scope. Explicit user `midday_rest_minutes` overrides the suggestion, including zero. Rest is taken nearby; returning to a hotel is not assumed without routes. Actual arrival/return windows constrain the rest interval and any shortened rest is noted. Preview budgets subtract meal/rest time; the provisional timeline and final plan show separate midday-rest entries. Durations cover sightseeing/photo/stroll/queue allowances, excluding separately scheduled lunch/rest. The generic fallback increased from 75 to 90 minutes, with other category estimates retained; it remains labelled, not a provider fact. Analysis signatures include a pacing version and applicable weather facts, so older estimates are not silently reused.

Recommendation size is chosen by the model from known days, scale, geography, leisure time and user needs. Results distinguish primary itinerary suggestions from alternatives without saving any selection. The old eight-item business cap is replaced by a 24-item per-batch technical bound and four-card display pages. Whole-batch identity/count is included in public reply context. Explicit more recommendations query the next provider batch, excluding already displayed IDs/names and chosen spots; a bounded retry can search the following provider page. A normal no-new-results reply preserves the old batch and selection. Chat requests misclassified as paging at the last page fall back to more recommendations; explicit UI page browsing retains its bounds. Additional recommendation queries preserve sightseeing confirmation. Validation: 294 backend tests and browser assistance, optional-room, recommendation-card/midday-rest/more-candidate fixtures passed. Model/vendor regression cases use synthetic responses.

## Guidance follows the current selection (2026-10-09)

`journey.next_step` treats unconfirmed sightseeing selection as the current activity before checking missing date/day/headcount information. While browsing/choosing spots, its message invites continued selection and defers missing inputs until selection is complete. Confirmed spots invite the inputs needed for hotel/date-specific queries. Reply prompts no longer require a `下一步：` heading, for either semantic goals or legacy responses. Explicit business results, transportation-confirmation messages and frontend banners/buttons use natural invitations while keeping actions, validation and clickable entries. Existing historical messages are not rewritten. Regression: 286 backend tests passed; assistance, optional hotel room and recommendation card browser fixtures passed.

## Preference discovery, recommendation facts and card prices (2026-10-09)

First general city recommendations with no known interests pause for an optional preference question. The workbench offers `暂无偏好，查看代表景点`; explicit default selection, named/topic queries, established recommendation batches and confirmed delegation can proceed. Preference state is scoped to the destination. `preference_mode=default` is a semantic intent field and a button argument, not keyword matching against a fixed user phrase. Default recommendations use city representative-place sources, map ratings and location/model comparison; the current API supplies no live popularity value, visitor counts or search index, so UI/replies do not claim a heat ranking.

`recommendation_context` adds explicitly supplied party notes (including elderly/mobility needs), numeric adult/child data and dated weather to recommendation reasoning. Only forecasts matching the saved destination/date/day identity and tour dates are included; uncovered dates stay unknown. The model may weigh walking, slopes, rests and indoor alternatives, without inferring unprovided ages, accessibility or ticket concessions. Missing-input invitations are polite and do not imply dates/headcount are required to browse spots.

`price_hints` computes spot/restaurant card labels from current snapshots. POI `cost` is reference per-person consumption, never assumed admission price; zero/missing values do not prove free entry. Adult admission interval minimum prices require the matching requested date/sales window and exclude child/addon products. A reviewed exact-name/city official admission policy can label free entry, with a 90-day recheck horizon and additional-service/availability caveats. Initial reviewed policy covers Qingdao Municipal Museum, sourced from its current `.cn` official website. Hotel selection and travel-wide budget accounting are unchanged. Verification: 282 backend tests and the isolated preference/default/card/detail browser fixture passed; new model/provider cases use synthetic responses.

## Hotel position and arrival continuity (2026-10-09)

Selected hotel identity and verified coordinates are independent of supplier quote freshness. Legacy selected-hotel `stale` and the explicit `quote_stale` mean expired date/occupancy pricing, not a missing route origin. `locations.selected_hotel` rejects explicit selection/location invalidation and destination mismatch; `hotel_anchor` additionally requires a valid, unambiguous coordinate. Hotel completion, remaining automatic selection and frontend step status share this distinction. Normalizing omitted children/ages/room defaults does not invalidate unchanged quotes or transport. Genuine date/occupancy changes still expire quotes and remove the old room selection.

Arrival events default to the selected hotel before sightseeing/meals, with luggage/check-in conditions unconfirmed. An arrival before the original queried check-in date explicitly names the uncovered arrival night and asks for availability/cost verification. Station-to-hotel transfer still uses the existing suggested 90-minute buffer, not a verified station route. Expired hotel prices are excluded from the calculated reference total. Missing hotel coordinates identify the hotel, dated meal and restaurant with existing clickable repair entries, preserving user choices. Regression: 275 backend tests and the optional-room/expired-quote browser fixture passed; provider responses in these new regression cases are isolated fixtures.

## Advisory confirmation and tour-only balancing (2026-10-08)

`visits.dates` remains the sole tour-date range: an earlier arrival day can appear in the full book as travel/rest, but is not a sightseeing day to fill. Workload imbalance and capacity based on suggested visit/transfer minutes are advisory, separated from identity/date validation. The model may improve a proposal once; a valid proposal with remaining estimates is retained rather than rejected. Warnings identify the specific compared dates and minutes without implying all other days are empty.

`app/plan_warnings.py` holds a checked candidate draft while a native confirmation dialog offers continue-with-warnings or adjust. Approval binds to the workspace input signature, expires after 15 minutes, publishes the cached result without repeating model generation, and preserves warnings in the book. Cancellation preserves selections/old plan. Candidate identity, explicit date validation, actual arrival/return incompatibilities and unresolved route/meal conflicts are not waived by generic workload consent. Local regression: 221 passed; browser consent/cancel/publication and history/map/ticket checks passed. Map architecture changes are only proposed, not implemented in this batch.

## Complete plan revision (2026-10-08)

`app/plan_revision.py` provides `optimize_plan`. A follow-up such as “帮我优化一下” after an existing plan or planning conflict revises the complete book, rather than only updating its sightseeing preview. Loading UI preserves the prior concrete conflict before replacement. Both visit analysis and final proposals receive the original plan, selected places/rooms/meals/transport, ticket and weather snapshots, official guides, user request and concrete repair feedback. Numeric family composition remains in model context; media and road geometry are omitted.

Only flexible dates, sequence, suggested durations/scope and notes can change. Generic optimization cannot apply model-invented requirements or new selections. Explicit pins, selected restaurants and tickets remain protected. Revision works on a private copy, verifies candidate coverage, time ordering, pins, day limits and inclusion of chosen meals, then publishes the new plan with a change summary. A bounded additional repair can use actual-route failure context; failure/cancellation leaves the original book and choices intact. Explicit spot date/order changes also regenerate an existing book after saving the user's requested pin.

Long continuous scenic visits crossing lunch are divided into one initial visit and a `spot_continue` segment. Total sightseeing duration is retained. Selected lunch plus travel to the restaurant and back is calculated separately; unavailable return routes are explicit errors, and re-entry conditions remain unverified. Timeline keys distinguish continuation segments. This is still a draft planning aid, not confirmation of opening, inventory or admission.

Member-three snapshot `dbfb52a` independently passes 274 tests but has reproduced per-night quote identity/date, cache invalidation and hard/soft period errors. Its new lodging orchestration has not been integrated. The active local application continues using its existing lodging model pending those fixes.

## Selection preview and estimated visit analysis (2026-10-08)

`app/visit_analysis.py`分析整个已选景点集合，而非直接沿用候选卡片的建议日期。完成景点选择、修改指定日期/顺序或点击时间轴“优化分配”时，模型结合位置、偏好、已知资料和交通时间预算建议时长、日期、时段与原因。程序检查真实已选ID、日期范围、用户明确安排、每日容量与可避免的负担失衡，允许一次修订。失败保留选择并显示带估算标签的分配；无模型结果时按地点类型估算，不再统一90分钟。模型知识只能用于建议玩法与时长，不能补造运营事实。

分析签名包含旅行条件、已选地点事实、指定日期/顺序、住宿位置和往返时刻；变化后旧分析失效。临时时间轴、餐饮参照区域和门票默认日期使用同一分配。正式提案收到同样的时间预算并做分配校验，支持半天/全天建议时长，再查询实际道路核对；交通接驳预留仍是当前估算规则，成员三的统一时间策略尚未合入。人数较少或负担过密按建议分钟数提示，不强制平均景点数量或擅自新增、删除选择。长行程仍分阶段最多16个景点生成。

详情地图只叠加当前旅行已选地点及当前查看地点；无选择时不把候选列表当已选点。静态高德底图scale=1实际投影使用512×2^zoom世界像素，前后端拟合、叠加、拖动与指针缩放统一；用高德实际绘制的交叉点校准13/15/17级，各级误差小于3个底图像素。地点标记为尖底圆头图钉，尖端落在坐标处。

截图中日照海洋公园169元、最低价日期2026-12-31及0天/0小时提前量，在2026-10-08实际途牛MCP响应中核对一致；不代表2026-10-12的成交报价或库存。界面明确区间起价、所选日期报价未确认与来源提前量的边界，字段缺失不补零。历史列表使用白底蓝字。

## Position and candidate access checks (2026-10-07, v11.2)

酒店列表来自途牛，地图坐标来自高德。途牛城市ID不能当高德citycode，也不猜测未注明坐标系的供应商经纬度。全部候选通过住宿类型、规范化分店名称和已提供的街道门牌交叉核对；同名歧义或门牌不符不接收坐标。地图地址可回填缺失字段，更新同步到已选住宿副本；旧记录可重试位置，生成前也补查缺位置的已选住宿。

餐厅、住宿及有已选区域参照的景点，在发布前做有限路段预检查。确认各方式均无方案、或餐次可用窗口连通行与完整用餐都无法容纳时筛除；连接失败、限流、缺城市代码、缺坐标与预算超时属于未知，保留并提示。检查结果记录参照点、坐标、餐次和查询时间，不是全程可行保证；最终计划仍按实际顺序复核。选择餐厅时重核当前上下文，旧查询结果不会替代当前日期与交通条件。

路线使用有效入口坐标，缺失或无效时用POI坐标；入口均无方案再核对POI位置。相同坐标无需请求零距离导航。公交分别传入起终点城市代码，无代码时只标公交待核实，不再默认青岛。高德真实网络请求间隔至少0.4秒、最多2个并发；候选批次20秒预算，超时回到未知而非不可通行。API空方案不等同于物理道路封闭。路线未核实会指出起终点并提供跳转信息，不通过改变用户选择掩盖失败。

帮助用户逐步确定旅行选择，形成有来源、能继续完善的旅行计划。

## Language

**旅行会话**：属于一个用户、围绕一次旅行展开的规划记录，包含需求、对话、候选与已选内容。一位用户可以保留多次旅行会话。
_Avoid_: 全站聊天记录、登录会话

**旅行计划书**：基于某个旅行会话中的选择和条件形成的每日安排与出发准备说明，未核实事项仍需确认。
_Avoid_: 已预订行程

**计划版本**：旅行条件与选择在某个时刻形成的记录；继续修改可能使此前的计划书需要更新。
_Avoid_: 新旅行

**选定**：用户在规划中选择某个景点、住宿或班次，表达意向，并不代表预订成功。
_Avoid_: 购买、已预订

**归档旅行**：暂不参与日常规划、仍可找回并继续的旅行会话。
_Avoid_: 删除旅行

## Selection semantics

**推荐班次**：从真实查询结果预填的去程/返程意向，selection_status为recommended，用户确认后才为confirmed。两种状态都未购票。

**房型方案**：一个当前酒店下的一条具体报价与房间数量，selected_room独立于酒店列表起价。已知容量由程序检查，未知入住政策仍需确认。

交通类型与方向分别控制；同一方向只有一个当前方案。改选要求明确替换，查询无结果不覆盖已选方案。

## Interaction and scheduling (2026-10-05, v5)

公开回复来自模型原生流式增量，经任务SSE传递；结构化意图和排程JSON仍在后台完成，不播放伪打字动画。刷新恢复同一任务，进度与已产生的正文保存。模型原始推理不展示，“处理过程”仅列实际执行步骤且默认折叠。

景点/房型选择、移除、分页和条件表单操作成功时只更新状态与短暂反馈，不追加助手消息；完成步骤或有新查询结果才产生有内容的回复。景点数量提示持续复用，最多三条浮窗。右侧可覆盖展开，保持对话原宽，点击遮罩收起。

仅给城市时先问偏好再说明初始景点；新会话提供目的地、日期和预算提示。明确给出的日期/人数先确认，再查数据；完成住宿只询问缺少的字段。日期确定且存在可用位置时自动查询天气，预报窗口之外不生成天气。高铁指G字头，动车／火车为其他返回车次；不改供应商参数。

计划书直接列日期与事件，不展示开头总结。建议交通时间加缓冲后按5分钟向上取整，建议游览时长按15分钟向上取整；班次真实时刻和地图原始估计保留。晚到当天安排休息；仍未核实的接驳时间明确是建议。旧计划需重新生成。

## Travel dates, dining and recommendations (2026-10-06, v6)

**游玩日期**：start_date起的days个日期。**去程/返程日期**：outbound_date、return_date独立保存；默认去程为start_date，默认返程为start_date加days，即游玩结束次日。用户明确日期优先；只修改返程不清空去程或住宿，但住宿报价覆盖期与新返程不一致要提示延住/退房/行李问题。已有班次不被默认日期静默替换。

**推荐批次**：模型根据偏好比较后发布的最多8个景点。界面分页只浏览这批，最多2页，不因下一页自动调用供应商扩展列表；重新筛选要显式发起请求。老会话的长列表按相同边界展示，已有选择保留。餐厅不能进入景点候选。

**用餐选择**：某个日期+早餐/午餐/晚餐意向；同餐次只有一个地点，改选覆盖，允许本餐或全部自行安排。主要选择完成后进入餐饮确认步骤，明确完成或自行安排后引导生成计划；用户主动直接生成仍可形成草稿。已选餐厅参与路线与排程检查，自行安排保留弹性时段。不是预订或实时营业保证。

主Agent提取意图，journey.py保护日期字段、持续偏好与唯一候选选择；foods.py通过高德MCP单独查餐厅和海鲜采购场所。事实数据来自真实API，未知人均/菜品不补造。回复只使用本轮结果与已存选择，避免下一步询问又罗列旧景点/天气。候选保存、推荐和用户确认分开；手动/自然语言明确选择后的交通是confirmed。

## Workbench and longer journeys (2026-10-07, v7)

**查询条件**：实际传给工具的类型、方向、日期、时段与车次类型；存为query_controls并通过任务SSE控制右侧。界面动画依次展示这些实际条件，不播放虚构点击。手动查询只更新工作台和右侧提示；对话查询保留回复。

**引用定位**：对话中的已知地点、酒店或房型名称可跳转到其工作台卡片；根据真实ID与消息中的酒店上下文定位，不自动选定。未知或歧义引用不生成虚构链接。

**景区分支**：优先使用高德parent与children字段归组。只有名字前缀时属于名称关联，须明确待核实；不猜父ID。主地点和子地点仍各自保留来源及选择，规划须考虑同日连续游览，避免重复全程计算。

**长行程阶段**：支持1–60个游玩日；模型每轮最多处理16个已选地点，逐段限定日期与ID并核对遗漏/重复。保存目录技术保护上限120地点，完整交通跨度90日；这些是运行边界，不表示5天或10景点是旅游可行性规则。过密与直线跨度明显时提示优先级，直线距离不得当道路距离；执行日程仍查路线并检查时间。跨城市多住宿/中途交通的完整优化仍未实现。

工作台只有一排景点、住宿、交通、餐饮、天气、计划导航。资料在标题旁弹窗，展开把手在面板外侧。选择不滚回顶部；右侧通知最多3条，旧通知更透明。首次确认完整往返时只补一条必要消息并切计划页。恢复码可以关闭或Esc稍后保存，当前页面保留查看入口，不写入浏览器持久存储。

餐饮优先按日期、餐次和当天景点或早餐住宿查找；无当日日程时比较主要游览区域的最多3个参照点，也可手动指定。缺少来源仍保持未知，不宣称订位或实时营业已核实。

## Detail cards, dated intentions and maps (2026-10-07, v8)

欢迎提示保存为新会话第一条助手消息，旧会话展示兼容欢迎提示。下一步先说明当前选择，再说明完成后的步骤；计划生成后引导查看与调整。餐饮不再被流程静默跳过，往返确认后进入餐饮并查询当前餐次的周边候选，明确自行安排同样完成步骤。

**详情卡片**：景点、住宿、餐饮缩略卡片点击打开详情弹窗，操作按钮仍独立执行。简介两行，不再内联展开；门票与预约在详情内，来源评分不写客流文案。图片只来自接口的photos/firstPic，不搜索盗用图片；无图或加载失败如实展示。房型、退改、位置与来源在住宿详情里，选房型保留主列表位置。

**游玩意向**：visit_requests按真实景点ID记录用户指定日期和morning/afternoon/evening/any；日期必须在游玩范围内，不能覆盖start_date。visit_suggestion是模型基于候选资料的灵活日期/时段建议。排程提案校验指定日期，程序核对上午/下午窗口、晚间时段、返程与时间冲突；夜间开放仍须核对。长行程分阶段同样保留意向。

**地图雏形**：标题旁地图入口展示真实坐标底图、地点列表及按天顺序示意；详情中展示单地点周边。高德静态图由鉴权服务端请求，密钥不下发。连线仅表示地点顺序，不宣称道路导航；无坐标或底图失败保留说明和外部地图入口。不是实时导航或JS交互地图。

住宿选择区域以已选景点坐标的中心参照点代替首项，并展示多地点直线位置比较；只核算实际查询的通行路线。餐饮参考日期意向/已生成日程、早餐住宿、午餐前后景点和晚餐游览/住宿区域；日期、餐次或手动参照变化重新查询，卡片突出有依据的推荐理由和人均。客流新闻预测仅评估，尚未实现。

## Responsive map camera (2026-10-07, v9)

底图仍来自高德Web服务，现有环境没有JS平台Key/安全配置。前端Canvas负责本地相机、地点标记和顺序线；拖动/滚轮/双击先更新画面，手势停止后获取1024×768底图，原图保留到新图加载。浏览器复用24幅图并预加载一幅全国底图；服务端复用HTTP连接、合并相同进行中请求、按LRU/字节预算缓存，地图响应private并按Cookie变化，密钥不下发。

“重置中心点”只恢复当前地图初始中心，保留比例；“显示全部”恢复中心和比例；“全国”切换中国中心与全国视野。主地图没有已选地点时也可看全国，支持全国范围拖动和1–17缩放；百分比以当前地图初始范围为100%。顺序线仍不代表道路几何。地图交互不写旅行需求或选择，网络更新失败可继续操作和重试。

## Provider data enrichment (2026-10-07, v10)

高德地点搜索与ID详情共用normalize_place，保留business的特色tag、alias、business_area、tel、cost、rating和分别标注的opentime_today/week，以及navi出入口与photos。空数组和空串转换为未知。place_detail为新业务动作；手动/弹窗自动补查均不调用回复模型，也不追加聊天，成功与失败保留当前场景、已选餐次、推荐理由、原有非空资料。首次打开已有高德ID的景点/餐饮补查一次；持久化状态避免反复请求，失败可手动重试。自然语言电话/营业资料问题可由submit_intent选择此动作并指定真实候选id。

酒店详情保存来源提供的房型，取消原每层列表8项截断，技术保护100项；详情字段白名单保留星级、品牌、评价汇总、面积、楼层、房型照片、餐食、cancelText/cancelDesc、可售count，移除预订凭据。儿童详情查询与搜索使用相同儿童人数/年龄条件。count=0的报价禁用，后端同样拦截，无count仍为未知。

门票日期优先手动visit_date、用户visit_requests、有效计划中的该景点日期、visit_suggestion、旅行首日。仅在查无结果时移除终端通用“博物馆/景区”等名称后缀重试一次，不把子景点扩大为父景点。保存产品ID、资源ID、人群、销售区间、最低价日期、退改提示、入园凭证、提前量与年龄资料；包含门票、其他产品、附加体验/餐食/商品分组，避免最低价文创挤掉后面的门票产品。startPrice始终作为区间起价，不推导指定日期准确报价或预约库存，销售区间不代表可预约。未查询、无产品和查询失败区别展示。

路线请求cost,navi,polyline，保存步行/驾车步骤和公交线路、站点、道路折线。计划可展开查看通行步骤；按日地图有折线时绘制实线，未查道路几何时保留明确的顺序示意。没有实现实时导航或全局最优路线。媒体与道路顶点从模型上下文剔除，事实仍完整保留在工作区与地图；避免长路线拖大模型输入。

验证：115项后端检查；browser_enrichment_v10.cjs与browser_map_v9.cjs独立场景通过，覆盖自动补查/成功失败静默/餐次选择保留/地图背景不切换/门票日期起价分类/无房/实际折线/既有地图手势与响应式布局。高德真实成都餐厅返回特色、电话、人均、评分、营业资料、3张照片；步行返回16分钟/1176米/5段步骤和道路几何。途牛实测“成都杜甫草堂博物馆”0项、“杜甫草堂”40项，混有附加商品且最低价日期为12-31，明确此数据边界。酒店历史供应商查询快照确认真实11房型响应曾被截成8，存在面积/楼层/图片/count/cancelDesc字段。真实模型选择place_detail且正确匹配餐厅ID，不修改旅行日期。未启用泛联网搜索、营销资料收集或客流新闻预测。

## V11 review integration (2026-10-07)

当前整合版保留浮动地图、悬停时间轴、逐餐选择和道路红线；兼容资料的date_scope/scope，图片安全策略只增加高德照片HTTP域名，脚本权限不扩大。餐次选择、时间轴共用到达后90分钟与返程前120分钟的窗口，并检查完整用餐时长；早餐、午餐、晚餐可在允许窗口内延后。完整路线仍在生成计划时查询核对，选择校验不冒充已核实道路接驳。先选餐后修改交通时保留用户选择，在餐厅和相关班次处标红，未排入的提示注明日期、餐次及店名。餐厅依旧按明确日期+餐次保存，不因景点重排而静默挪期。


## Data and knowledge service upgrade (2026-10-08)

数据侧新增Qdrant持久化本地模式与服务端连接、FastEmbed中文512维ONNX模型、父子切分、BM25与向量召回及RRF融合。索引按完整代次原子发布、缓存未变化片段的向量，索引与语料/模型/后端身份不一致时明确降级；运行时不自动下载模型。当前电脑尚未部署Qdrant Rust服务端，多Worker须改用服务端连接。

官方来源注册表和正文选择器受控采集，内容版本、采集状态、来源、实体和适用区间随文档保留；失败保留正文、历史归档独立保存。补充成都杜甫草堂、熊猫基地、杭州西湖与西安城墙正文。旧青岛博物馆资料为未完成更新的快照，旧崂山10月5日临时公告限定当日，不当作当前或未来运营事实。

retrieve_guides新增visit_date/end_date区间及可选严格entity_ids过滤，返回上下文与适用状态；discovery/planning只增加日期范围透传，不改变排程语义。search_transport_places返回站点/机场/航站楼真实坐标候选，排除周边商店和其他名称的机场，候选并非已确认接驳端点。地点新增_data质量元数据，坐标无效保持未知，原有有效坐标字符串保留。

MCP启动前预加载Qdrant原生数值依赖，修复Windows在stdio读线程启动后延迟导入NumPy的等待；生命周期显式关闭本地向量库。应用和验证脚本显式透传数据侧环境配置，避免MCP的默认环境白名单丢失QDRANT_URL等配置。

平台数据库、独立Worker、地图SDK、日期理解和动态时间计算继续由成员二/三分支开发。接入方式、边界与初始化命令见docs/collaboration/数据与知识服务接入说明.md。

## Shandong public scenery corpus (2026-10-08)

按用户要求适量扩充山东数据，本批停止在52条记录：文化和旅游部16条景区和7条旅游度假区目录，加29篇地方官方及公共机构正文，覆盖省内16个地市。50条仅用于特色和历史背景，2条运营说明仍标为出游日待核实；不声称票务、开放状态或实时客流已全部覆盖。旧线路裁去美食和历史公交，地方志仅截取相关景观段落；未知简介、未核对坐标系和源站失败如实保留。

新增15个来源可追溯的城市推荐，原有青岛及其他三城保持，共19城。knowledge schema升级为3，city_aliases支持已核对的曲阜等县市，不将全地市正文自动当作县域资料；公开目录只解析静态字面量，受控采集检查robots、证书与跳转域名，失败保留旧版。未启用开放网页搜索或持续爬虫。

验证：181项后端测试通过，真实MCP检索新增济南/泰安/曲阜/滨州/日照/威海6场景通过，原有检索与日期隔离同样通过。全语料90记录、78父块、181子块，已重新构建实际中文Embedding/Qdrant索引。详见docs/collaboration/山东景区资料覆盖说明.md。

## Semantic goals and query latency (2026-10-08)

对话新增mission语义目标与app/goal_agent.py受控工具观察循环，最多四次后续决策；查询/咨询/解释与代选/计划修订分别处理，有效语义任务不再被旧关键词修正规则覆盖。代选包括目的地，缺项建议与本轮明确条件均先展示确认后采用，车票机票保持用户手选。当前查询不能同时保存两套跨城市对比行程，与已选条件冲突时澄清而不清空旧选择。

app/request_cache.py提供进程内相同请求合并、取消等待者隔离及HTTP连接复用；推荐按完整条件与事实缓存600秒，简单查询及连续查询完成回复减少额外模型调用。任务进度可以提前展示当前旅行的基础候选，再补推荐与通行检查；不覆盖已选状态，最终结果仍以任务完整保存为准。途牛限流、预算及正式规划事实核对保留；Worker的跨进程限流仍待平台侧接入。

236项后端回归、确认与候选预览浏览器验证、历史/地图/门票浏览器验证通过；真实模型3种表达与合成供应商工具续查通过。详见docs/collaboration/语义任务执行与查询提速说明.md，运行记录位于忽略的data/runtime，不将夹具结果声称为真实供应商全流程验收。

## Optional room selection (2026-10-08)

住宿步骤仅要求选定有效酒店，具体房型为可选项。complete_hotel不再自动查询或选择房型，next_step、工作台步骤状态和继续按钮依据酒店有效性判断。用户主动选房型时保留原有可售、人数与房间数校验；过期酒店仍需重新确认。

自动配置默认只选择住宿位置，补齐模式保留已有有效酒店和已选房型，不因房型缺失补选。计划书仍使用酒店坐标计算往返路线，未选房型时将具体房型及实际住宿总价列为可选待核实，列表起价仅用于参考预算。导出说明和对话提示同步标注房型可选。新增测试覆盖无房型继续、自动配置保留酒店、无房型服务依赖及计划路线锚点；浏览器验证酒店选择后按钮启用、步骤完成状态和主动房型选择。

## Selective member integration (2026-10-09)

固定复核成员二42a6e28、成员三90de7f2。独立吸收最新Repository/JobContext公共契约与语义夹具、餐饮关键词/5至10公里/城市范围兜底与单餐取消，不启用MySQL或Worker。保留通行筛选与提前候选预览；供应商查询失败停止兜底并保留旧候选，范围与适配器实际发送值一致。补充阶段夹具原子写入竞态回归、撤销返回及额度申请口径。

完整平台与逐晚规划暂不吸收：实际Worker最终发布未封住取消/租约/版本，新旅行存储与MySQL任务外键未对接，业务阶段恢复未接入；逐晚住宿的界面分配与计划、路线、预算仍不一致。另有额度并发、知识过滤/日期范围与导入版本问题。详见docs/collaboration/分支整合复核与待修事项-20261009.md，PR #2保持待修。接口夹具通过不代表完整业务迁移完成。
