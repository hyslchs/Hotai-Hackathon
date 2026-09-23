import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchRecommendation, fetchRideEstimate, recordFeedback } from "../api/recommendations";
import { demoLocations } from "../mocks/taipeiDemo";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("recommendation API client", () => {
  it("normalizes safe API data and retains source", async () => {
    vi.stubEnv("VITE_BACKEND_URL", "http://api.test");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      request_id: "rec_test", model_version: "test-v1", restaurant_source: "google_places",
      warnings: [], restaurants: [{
        rank: 1, place_id: "place-1", name: "測試餐廳",
        location: { latitude: 25.05, longitude: 121.52 }, rating: 4.5, review_count: 10,
        open_status: "open", distance_km: 2.1, estimated_travel_time_min: 9,
        score: 0.8, score_breakdown: { area_attraction: 0.8, similar_riders: null, personal_mobility: 0.9 },
        explanation: "依區域與距離證據排序。",
      }],
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchRecommendation(demoLocations[0], "full");

    expect(result?.source).toBe("google_places");
    expect(result?.restaurants[0].id).toBe("place-1");
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/v1/recommendations");
  });

  it("returns null for a failed backend so the UI can use local fallback", async () => {
    vi.stubEnv("VITE_BACKEND_URL", "http://api.test");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 503 })));

    await expect(fetchRecommendation(demoLocations[0], "cold")).resolves.toBeNull();
  });

  it("requests a historical estimate and sends safe feedback only for API recommendations", async () => {
    vi.stubEnv("VITE_BACKEND_URL", "http://api.test");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        distance_km: 2.5, estimated_travel_time_min: 11,
        fare_estimate: { lower: 120, upper: 180, label: "依 Train 歷史行程估算，非 yoxi 官方報價。" },
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ recorded: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const recommendation = {
      requestId: "rec_0123456789abcdef", modelVersion: "test-v1", source: "google_places" as const,
      fallbackUsed: false, modelName: "area_a_plus_c", warning: "", restaurants: [{
        id: "place-1", rank: 1, name: "測試餐廳", areaName: "Taipei", distanceKm: 2.5,
        travelTimeMin: 11, score: 0.8, rating: 4.5, reviewCount: 10, openStatus: "open" as const,
        coordinates: { latitude: 25.05, longitude: 121.52 }, reason: "依區域證據推薦。",
        scoreBreakdown: { area_attraction: 0.8, personal_mobility: 0.9 },
      }],
    };

    const estimate = await fetchRideEstimate(recommendation, demoLocations[0], recommendation.restaurants[0]);
    await recordFeedback(recommendation.requestId, recommendation.restaurants[0].id, "ride_clicked");

    expect(estimate?.fare?.lower).toBe(120);
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/v1/ride/estimate");
    expect(fetchMock.mock.calls[1][0]).toBe("http://api.test/api/v1/feedback");
    expect(fetchMock.mock.calls[1][1].body).not.toContain("RiderId");
  });
});
