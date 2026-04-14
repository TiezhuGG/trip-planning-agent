import { formatDate } from "../utils/tripPlannerForm"
import type { TripPlanningRequest } from "../types/planning"

export const plannerInterestOptions = [
  "\u81ea\u7136\u98ce\u5149",
  "\u5386\u53f2\u6587\u5316",
  "\u7f8e\u98df\u63a2\u7d22",
  "\u62cd\u7167\u6253\u5361",
  "\u591c\u6e38\u4f11\u95f2",
  "\u827a\u672f\u5c55\u89c8",
]

export const plannerTransportOptions = [
  "\u516c\u5171\u4ea4\u901a",
  "\u6253\u8f66",
  "\u81ea\u9a7e",
  "\u6b65\u884c",
  "\u9a91\u884c",
]

export const plannerHotelOptions = [
  "\u7ecf\u6d4e\u578b\u9152\u5e97",
  "\u8212\u9002\u578b\u9152\u5e97",
  "\u7cbe\u54c1\u6c11\u5bbf",
  "\u9ad8\u7aef\u5ea6\u5047\u9152\u5e97",
]

export const plannerPaceOptions: Array<{
  label: string
  value: TripPlanningRequest["pace"]
}> = [
  { label: "\u8f7b\u677e", value: "relaxed" },
  { label: "\u5747\u8861", value: "balanced" },
  { label: "\u7d27\u51d1", value: "intense" },
]

export const plannerBudgetOptions: Array<{
  label: string
  value: TripPlanningRequest["budget_level"]
}> = [
  { label: "\u7ecf\u6d4e\u578b", value: "economy" },
  { label: "\u8212\u9002\u578b", value: "comfort" },
  { label: "\u54c1\u8d28\u578b", value: "luxury" },
]

export const plannerStageOptions = [
  "\u751f\u6210\u521d\u6b65\u8ba1\u5212",
  "\u641c\u7d22\u666f\u70b9\u4e0e\u9910\u996e",
  "\u83b7\u53d6\u5929\u6c14\u4e0e\u8def\u7ebf",
  "\u6574\u5408\u6700\u7ec8\u884c\u7a0b",
]

export function createInitialTripPlanningRequest(): TripPlanningRequest {
  const today = formatDate(new Date())
  return {
    origin: "",
    destination: "",
    start_date: today,
    days: 3,
    interests: ["\u81ea\u7136\u98ce\u5149"],
    must_visit: [],
    pace: "balanced",
    budget_level: "comfort",
    transport_preferences: [],
    hotel_style: "\u8212\u9002\u578b\u9152\u5e97",
    dining_preferences: [],
    travelers: { adults: 1, children: 0, seniors: 0 },
    notes: "",
  }
}
