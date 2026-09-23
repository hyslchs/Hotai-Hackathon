import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import App from "../App";
import { demoFlowReducer, initialDemoFlowState } from "../app/demoMachine";
import { buildDemoRecommendation, demoLocations } from "../mocks/taipeiDemo";

describe("Taipei Demo app", () => {
  it("renders a clear home without technical details or server-only secrets", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("今晚，換個方向吃飯");
    expect(html).toContain("非官方示範");
    expect(html).not.toContain("fallback");
    expect(html).not.toContain("GOOGLE_PLACES_API_KEY");
    expect(html).not.toContain("LLM_API_KEY");
  });

  it("supports the required deterministic screen transitions", () => {
    const selecting = demoFlowReducer(initialDemoFlowState, { type: "START" });
    const loading = demoFlowReducer(selecting, { type: "RECOMMEND" });
    const results = demoFlowReducer(loading, { type: "RECOMMENDATION_READY" });
    const detail = demoFlowReducer(results, { type: "OPEN_RESTAURANT", restaurantId: "demo-place-1" });
    const ride = demoFlowReducer(detail, { type: "CONFIRM_RIDE" });

    expect([selecting.screen, loading.screen, results.screen, detail.screen, ride.screen]).toEqual([
      "LOCATION_SELECTION",
      "RECOMMENDING",
      "RESULTS",
      "RESTAURANT_DETAIL",
      "RIDE_CONFIRMATION",
    ]);
  });

  it("marks fallback and synthetic restaurant data explicitly", () => {
    const fallbackLocation = demoLocations.find((item) => item.fallback);
    expect(fallbackLocation).toBeDefined();
    const response = buildDemoRecommendation(fallbackLocation!, "cold");

    expect(response.fallbackUsed).toBe(true);
    expect(response.source).toBe("demo_fixture");
    expect(response.warning).toContain("示範餐廳");
    expect(response.restaurants).toHaveLength(5);
    expect(response.restaurants.every((item) => item.id.startsWith("demo-place-"))).toBe(true);
  });

  it("keeps disabled or unavailable personalization components unavailable instead of zero", () => {
    const cold = buildDemoRecommendation(demoLocations[0], "cold");
    const full = buildDemoRecommendation(demoLocations[0], "full");
    expect(cold.restaurants[0].scoreBreakdown.similar_riders).toBeNull();
    expect(cold.restaurants[0].scoreBreakdown.personal_mobility).toBeNull();
    expect(full.restaurants[0].scoreBreakdown.similar_riders).toBeNull();
  });
});
