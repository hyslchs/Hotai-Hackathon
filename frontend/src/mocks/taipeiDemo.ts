import type { PersonaId } from "../app/demoMachine";

export interface DemoLocation {
  id: string;
  name: string;
  detail: string;
  latitude: number;
  longitude: number;
  fallback: boolean;
  simulateError?: boolean;
}

export interface DemoRestaurant {
  id: string;
  rank: number;
  name: string;
  areaName: string;
  distanceKm: number;
  travelTimeMin: number;
  score: number;
  rating: number | null;
  reviewCount: number | null;
  openStatus: "open" | "closed" | "unknown";
  coordinates: { latitude: number; longitude: number };
  sourceAreaId?: string;
  areaScore?: number;
  reason: string;
  scoreBreakdown: Record<string, number | null>;
}

export interface DemoRecommendation {
  requestId: string;
  modelVersion: string;
  source: "demo_fixture" | "google_places";
  fallbackUsed: boolean;
  modelName: string;
  warning: string;
  restaurants: DemoRestaurant[];
  calculation?: {
    originAssignment?: {
      distanceBudgetKm: number;
      proximityWeight: number;
    };
    topAreas: Array<{
      rank: number;
      areaId: string;
      centroid: { latitude: number; longitude: number };
      radiusKm: number;
      score: number;
    }>;
    stages: Array<{ name: string; durationMs?: number; [key: string]: unknown }>;
  };
}

export const personaOptions: Array<{ id: PersonaId; name: string; detail: string }> = [
  { id: "full", name: "常出門", detail: "適合熟悉台北的你" },
  { id: "light", name: "偶爾出門", detail: "換個地方走走" },
  { id: "cold", name: "第一次使用", detail: "從熱門去處開始" },
];

export const demoLocations: DemoLocation[] = [
  {
    id: "taipei-main-station",
    name: "台北車站",
    detail: "台北市中心",
    latitude: 25.0478,
    longitude: 121.517,
    fallback: false,
  },
  {
    id: "taipei-fallback-probe",
    name: "北海岸附近",
    detail: "從較遠的地方出發",
    latitude: 25.399,
    longitude: 121.999,
    fallback: true,
  },
  {
    id: "service-outage",
    name: "暫時無法使用的位置",
    detail: "請換個位置試試",
    latitude: 25.0478,
    longitude: 121.517,
    fallback: false,
    simulateError: true,
  },
];

const restaurantSeeds = [
  ["暮色小館", "中山區", 3.8, 14, 0.89, 25.0521, 121.5222],
  ["島嶼食堂", "大安區", 5.6, 19, 0.84, 25.0338, 121.5434],
  ["拾光麵屋", "松山區", 6.2, 21, 0.8, 25.0516, 121.5572],
  ["山海餐桌", "萬華區", 4.1, 16, 0.76, 25.0368, 121.5029],
  ["日常咖哩所", "信義區", 7.4, 24, 0.72, 25.0332, 121.5651],
] as const;

export function buildDemoRecommendation(
  location: DemoLocation,
  persona: PersonaId,
): DemoRecommendation {
  const personaReason =
    persona === "cold"
      ? "這一帶是晚餐時段可以考慮的去處。"
      : "這一帶適合晚餐時段前往，車程也在你常見的出行範圍內。";
  const fallbackText = location.fallback
    ? "從這裡出發，也可以看看台北這一帶的餐廳。"
    : personaReason;

  return {
    requestId: `demo-${location.id}-${persona}`,
    modelVersion: "taipei-area-v1-49594cb830f5-b589b2a59c6a-250-25-eom",
    source: "demo_fixture",
    fallbackUsed: location.fallback,
    modelName: location.fallback ? "area_attraction_fallback" : "origin_period_popularity",
    warning: "這些是示範餐廳，名稱與行程資訊僅供體驗。",
    restaurants: restaurantSeeds.map(
      ([name, areaName, distanceKm, travelTimeMin, score, latitude, longitude], index) => ({
        id: `demo-place-${index + 1}`,
        rank: index + 1,
        name,
        areaName,
        distanceKm: location.fallback ? distanceKm + 1.2 : distanceKm,
        travelTimeMin: location.fallback ? travelTimeMin + 4 : travelTimeMin,
        score: persona === "cold" ? Math.max(score - 0.04, 0) : score,
        rating: 4.6 - index * 0.1,
        reviewCount: 680 - index * 77,
        openStatus: index === 4 ? "unknown" : "open",
        coordinates: { latitude, longitude },
        reason: fallbackText,
        scoreBreakdown: {
          area_attraction: Number((score - 0.03).toFixed(2)),
          origin_period_popularity: Number(score.toFixed(2)),
          similar_riders: null,
          personal_mobility: persona === "cold" ? null : 0.82 - index * 0.05,
        },
      }),
    ),
    calculation: {
      topAreas: [],
      stages: [
        { name: "area_ranking" },
        { name: "restaurant_search" },
        { name: "route_estimation" },
        { name: "restaurant_ranking" },
      ],
    },
  };
}
