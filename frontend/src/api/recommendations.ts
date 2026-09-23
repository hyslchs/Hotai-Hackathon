import type { PersonaId } from "../app/demoMachine";
import type { DemoLocation, DemoRecommendation, DemoRestaurant } from "../mocks/taipeiDemo";

const aliases: Record<PersonaId, string> = { full: "demo_rider_full", light: "demo_rider_light", cold: "demo_rider_cold" };

export async function fetchRecommendation(location: DemoLocation, persona: PersonaId, at = "2026-09-17T18:30:00+08:00"): Promise<DemoRecommendation | null> {
  const baseUrl = import.meta.env.VITE_BACKEND_URL;
  if (!baseUrl || location.simulateError) return null;
  const response = await fetch(baseUrl + "/api/v1/recommendations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rider_alias: aliases[persona], location: { name: location.name, latitude: location.latitude, longitude: location.longitude }, datetime: at }),
  });
  if (!response.ok) return null;
  const body = await response.json() as any;
  return {
    requestId: body.request_id, modelVersion: body.model_version,
    source: body.restaurant_source === "google_places" ? "google_places" : "demo_fixture",
    fallbackUsed: location.fallback || body.restaurant_source !== "google_places",
    modelName: "area_a_plus_c", warning: body.warnings.join(" "),
    restaurants: body.restaurants.map((restaurant: any): DemoRestaurant => ({
      id: restaurant.place_id, rank: restaurant.rank, name: restaurant.name,
      areaName: "台北市", distanceKm: restaurant.distance_km,
      travelTimeMin: restaurant.estimated_travel_time_min, score: restaurant.score,
      rating: restaurant.rating, reviewCount: restaurant.review_count,
      openStatus: restaurant.open_status, coordinates: restaurant.location,
      reason: restaurant.explanation, scoreBreakdown: restaurant.score_breakdown,
      sourceAreaId: restaurant.source_area_id, areaScore: restaurant.area_score,
    })),
    calculation: body.calculation ? {
      originAssignment: body.calculation.origin_assignment ? {
        distanceBudgetKm: body.calculation.origin_assignment.distance_budget_km,
        proximityWeight: body.calculation.origin_assignment.proximity_weight,
      } : undefined,
      topAreas: body.calculation.top_areas.map((area: any) => ({
        rank: area.rank, areaId: area.area_id, centroid: area.centroid,
        radiusKm: area.radius_km, score: area.score,
      })),
      stages: body.calculation.stages.map((stage: any) => ({
        ...stage, durationMs: stage.duration_ms,
      })),
    } : undefined,
  };
}

export interface RideEstimate {
  distanceKm: number;
  travelTimeMin: number;
  fare: { lower: number; upper: number; label: string } | null;
  encodedPolyline: string | null;
  routeNotice: string;
}

export type FeedbackAction = "impression" | "restaurant_clicked" | "explanation_opened" | "ride_clicked";

export async function fetchRideEstimate(
  recommendation: DemoRecommendation,
  location: DemoLocation,
  restaurant: DemoRestaurant,
  at = "2026-09-17T18:30:00+08:00",
): Promise<RideEstimate | null> {
  const baseUrl = import.meta.env.VITE_BACKEND_URL;
  if (!baseUrl || recommendation.requestId.startsWith("demo-")) return null;
  const response = await fetch(baseUrl + "/api/v1/ride/estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      request_id: recommendation.requestId,
      place_key: restaurant.id,
      origin: { name: location.name, latitude: location.latitude, longitude: location.longitude },
      destination: { name: restaurant.name, latitude: restaurant.coordinates.latitude, longitude: restaurant.coordinates.longitude },
      datetime: at,
    }),
  });
  if (!response.ok) return null;
  const body = await response.json() as any;
  return {
    distanceKm: body.distance_km,
    travelTimeMin: body.estimated_travel_time_min,
    fare: body.fare_estimate ? {
      lower: body.fare_estimate.lower,
      upper: body.fare_estimate.upper,
      label: body.fare_estimate.label,
    } : null,
    encodedPolyline: body.encoded_polyline ?? null,
    routeNotice: body.route_notice ?? "此為目前建議路線，不是歷史車輛軌跡。",
  };
}

export async function recordFeedback(
  requestId: string,
  placeKey: string,
  action: FeedbackAction,
): Promise<void> {
  const baseUrl = import.meta.env.VITE_BACKEND_URL;
  if (!baseUrl || requestId.startsWith("demo-")) return;
  try {
    await fetch(baseUrl + "/api/v1/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: requestId, place_key: placeKey, action }),
    });
  } catch {
    // Interaction telemetry is best-effort and must never interrupt the demo.
  }
}
