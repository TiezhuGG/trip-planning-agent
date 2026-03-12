from app.schemas.planning import InitialPlanDraft, POIRecommendation, TripPlanningRequest


class MealRecommendationAgent:
    def gather(
        self,
        request: TripPlanningRequest,
        initial_plan: InitialPlanDraft,
        restaurants: list[POIRecommendation],
    ) -> dict[int, list[POIRecommendation]]:
        if not restaurants:
            return {}

        day_meals: dict[int, list[POIRecommendation]] = {}
        for day_index, day in enumerate(initial_plan.days):
            start_index = day_index % len(restaurants)
            selected: list[POIRecommendation] = []
            for offset in range(len(restaurants)):
                restaurant = restaurants[(start_index + offset) % len(restaurants)]
                if restaurant in selected:
                    continue
                selected.append(restaurant)
                if len(selected) >= 2:
                    break
            day_meals[day.day_number] = selected

        if not day_meals:
            for day_index in range(request.days):
                day_meals[day_index + 1] = [restaurants[day_index % len(restaurants)]]
        return day_meals
