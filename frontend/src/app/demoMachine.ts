export type DemoScreen = "HOME" | "LOCATION_SELECTION" | "RECOMMENDING" | "RESULTS" | "RESTAURANT_DETAIL" | "RIDE_CONFIRMATION" | "ERROR";

export type PersonaId = "full" | "light" | "cold";

export interface DemoFlowState {
  screen: DemoScreen;
  persona: PersonaId;
  locationId: string;
  selectedRestaurantId: string | null;
  errorMessage: string | null;
}

export type DemoFlowAction =
  | { type: "START" }
  | { type: "BACK_HOME" }
  | { type: "SELECT_PERSONA"; persona: PersonaId }
  | { type: "SELECT_LOCATION"; locationId: string }
  | { type: "RECOMMEND" }
  | { type: "RECOMMENDATION_READY" }
  | { type: "RECOMMENDATION_FAILED"; message: string }
  | { type: "OPEN_RESTAURANT"; restaurantId: string }
  | { type: "BACK_RESULTS" }
  | { type: "CONFIRM_RIDE" }
  | { type: "RETRY" };

export const initialDemoFlowState: DemoFlowState = {
  screen: "HOME",
  persona: "full",
  locationId: "taipei-main-station",
  selectedRestaurantId: null,
  errorMessage: null,
};

export function demoFlowReducer(state: DemoFlowState, action: DemoFlowAction): DemoFlowState {
  switch (action.type) {
    case "START":
      return { ...state, screen: "LOCATION_SELECTION", errorMessage: null };
    case "BACK_HOME":
      return { ...initialDemoFlowState, persona: state.persona };
    case "SELECT_PERSONA":
      return { ...state, persona: action.persona };
    case "SELECT_LOCATION":
      return { ...state, locationId: action.locationId };
    case "RECOMMEND":
    case "RETRY":
      return { ...state, screen: "RECOMMENDING", selectedRestaurantId: null, errorMessage: null };
    case "RECOMMENDATION_READY":
      return { ...state, screen: "RESULTS", errorMessage: null };
    case "RECOMMENDATION_FAILED":
      return { ...state, screen: "ERROR", errorMessage: action.message };
    case "OPEN_RESTAURANT":
      return { ...state, screen: "RESTAURANT_DETAIL", selectedRestaurantId: action.restaurantId };
    case "BACK_RESULTS":
      return { ...state, screen: "RESULTS", selectedRestaurantId: null };
    case "CONFIRM_RIDE":
      return { ...state, screen: "RIDE_CONFIRMATION" };
    default:
      return state;
  }
}
