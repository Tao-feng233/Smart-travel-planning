// core/state.js
let suppressMealAdvance = 0;

let workspace = null,
  tab = "spot",
  busy = false,
  renderedMessages = "",
  detailOpenId = null,
  jobUI = null,
  destinationPage = 1,
  transportMode = "train",
  transportDirection = "outbound",
  trainType = "all",
  timeStart = "",
  timeEnd = "",
  replaceTarget = null,
  liveReply = "",
  liveSteps = [],
  workbenchExpanded = false,
  transportDates = {},
  mealDate = "",
  mealPeriod = "lunch",
  foodAnchor = "",
  pickedHotelOpen = null,
  pendingSettledNight = null,
  stayOpenDate = "",
  settledNight = "";

const actionViews = {
  discover_destinations: "spot",
  choose_destination: "spot",
  spots_page: "spot",
  dismiss_spot: "spot",
  complete_spots: "hotel",
  complete_hotel: "transport",
  skip_hotel: "transport",
  plan: "plan",
  optimize_plan: "plan",
  complete_food: "plan",
  visit_schedule: "spot",
  search_foods: "food",
  meal_choice: "food",
  search_hotels: "hotel",
  hotel_detail: "hotel",
  select_room: "hotel",
  train: "transport",
  flight: "transport",
  search_spots: "spot",
  ticket: "spot",
  weather: "weather",
  transport_arrangement: "food",
};

const sceneNames = {
  spot: "目的地与景点",
  hotel: "住宿选择",
  transport: "往返交通",
  weather: "天气",
  plan: "旅行计划书",
  knowledge: "资料与依据",
  food: "餐饮选择",
  map: "旅行地图",
};

const $ = (s) => document.querySelector(s);

const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );

const mode = (m) =>
  ({ walking: "步行", driving: "驾车 / 打车", transit: "公交 / 地铁" })[m] || m;

const disabledBeforeBusy = new WeakMap();

let printSources = [];
