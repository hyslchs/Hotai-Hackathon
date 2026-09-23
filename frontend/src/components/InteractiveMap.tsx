import { useEffect, useRef, useState } from "react";
import type { DemoRestaurant } from "../mocks/taipeiDemo";

type Coordinate = { latitude: number; longitude: number };
type RankedArea = { rank: number; areaId: string; centroid: Coordinate; radiusKm: number; score: number };

declare global {
  interface Window { google?: any; }
}

let mapsLoader: Promise<void> | null = null;

function loadGoogleMaps(apiKey: string): Promise<void> {
  if (window.google?.maps) return Promise.resolve();
  if (mapsLoader) return mapsLoader;
  mapsLoader = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly&libraries=geometry`;
    script.async = true;
    script.onload = () => window.google?.maps ? resolve() : reject(new Error("Google Maps 載入失敗"));
    script.onerror = () => reject(new Error("Google Maps 無法連線"));
    document.head.append(script);
  });
  return mapsLoader;
}

export function InteractiveMap({
  origin,
  restaurants,
  activeId,
  areas = [],
  encodedPolyline,
  onOriginChange,
  onRestaurantSelect,
}: {
  origin: Coordinate;
  restaurants: DemoRestaurant[];
  activeId?: string | null;
  areas?: RankedArea[];
  encodedPolyline?: string | null;
  onOriginChange: (coordinate: Coordinate) => void;
  onRestaurantSelect: (restaurantId: string) => void;
}) {
  const elementRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]);
  const [mapState, setMapState] = useState<"loading" | "ready" | "fallback">(
    import.meta.env.VITE_GOOGLE_MAPS_BROWSER_API_KEY ? "loading" : "fallback",
  );
  const browserKey = import.meta.env.VITE_GOOGLE_MAPS_BROWSER_API_KEY as string | undefined;

  useEffect(() => {
    if (!browserKey || !elementRef.current) return;
    let active = true;
    void loadGoogleMaps(browserKey).then(() => {
      if (!active || !elementRef.current) return;
      mapRef.current = new window.google.maps.Map(elementRef.current, {
        center: { lat: origin.latitude, lng: origin.longitude }, zoom: 13,
        disableDefaultUI: true, zoomControl: true, clickableIcons: false,
      });
      mapRef.current.addListener("click", (event: any) => {
        onOriginChange({ latitude: event.latLng.lat(), longitude: event.latLng.lng() });
      });
      setMapState("ready");
    }).catch(() => { if (active) setMapState("fallback"); });
    return () => { active = false; };
  }, [browserKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || mapState !== "ready") return;
    overlaysRef.current.forEach((overlay) => overlay.setMap?.(null));
    const overlays: any[] = [];
    const maps = window.google.maps;
    const originMarker = new maps.Marker({
      map, position: { lat: origin.latitude, lng: origin.longitude }, title: "目前位置", label: "我",
      icon: { path: maps.SymbolPath.CIRCLE, scale: 9, fillColor: "#2864ff", fillOpacity: 1, strokeColor: "#ffffff", strokeWeight: 3 },
    });
    overlays.push(originMarker);
    areas.forEach((area) => overlays.push(new maps.Circle({
      map, center: { lat: area.centroid.latitude, lng: area.centroid.longitude },
      radius: Math.max(area.radiusKm, 0.2) * 1000, fillColor: "#ffd800", fillOpacity: 0.08,
      strokeColor: "#9f8100", strokeOpacity: 0.45, strokeWeight: 1,
    })));
    restaurants.forEach((restaurant) => {
      const marker = new maps.Marker({
      map, position: { lat: restaurant.coordinates.latitude, lng: restaurant.coordinates.longitude },
      title: restaurant.name, label: String(restaurant.rank),
      zIndex: restaurant.id === activeId ? 20 : 10,
      animation: restaurant.id === activeId ? maps.Animation.DROP : undefined,
      });
      marker.addListener("click", () => onRestaurantSelect(restaurant.id));
      overlays.push(marker);
    });
    if (encodedPolyline && maps.geometry?.encoding) {
      overlays.push(new maps.Polyline({
        map, path: maps.geometry.encoding.decodePath(encodedPolyline), strokeColor: "#e95f27",
        strokeOpacity: 0.9, strokeWeight: 5,
      }));
    }
    overlaysRef.current = overlays;
    const selected = restaurants.find((restaurant) => restaurant.id === activeId);
    if (selected) map.panTo({ lat: selected.coordinates.latitude, lng: selected.coordinates.longitude });
  }, [activeId, areas, encodedPolyline, mapState, onRestaurantSelect, origin, restaurants]);

  if (mapState === "fallback") {
    return (
      <section className="map-canvas static-map" aria-label="台北位置示意圖">
        <div className="map-grid" aria-hidden="true" /><div className="map-road road-one" aria-hidden="true" /><div className="map-road road-two" aria-hidden="true" />
        <div className="current-pin" aria-label="地圖定位標記"><span /></div>
        {restaurants.map((restaurant, index) => <div aria-label={`${restaurant.rank}. ${restaurant.name}`} className={`restaurant-pin pin-${index + 1} ${activeId === restaurant.id ? "is-active" : ""}`} key={restaurant.id}><span>{restaurant.rank}</span></div>)}
        <p className="map-caption">位置示意圖</p>
      </section>
    );
  }
  return <section className="map-canvas" aria-label="可點選的台北地圖"><div className="google-map" ref={elementRef} />{mapState === "loading" ? <p className="map-caption">正在開啟地圖…</p> : null}</section>;
}
