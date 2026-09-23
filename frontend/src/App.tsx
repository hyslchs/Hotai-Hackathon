import { useEffect, useMemo, useReducer, useState } from "react";
import { demoFlowReducer, initialDemoFlowState, type PersonaId } from "./app/demoMachine";
import {
  buildDemoRecommendation,
  demoLocations,
  personaOptions,
  type DemoLocation,
  type DemoRecommendation,
  type DemoRestaurant,
} from "./mocks/taipeiDemo";
import { fetchRecommendation, fetchRideEstimate, recordFeedback, type RideEstimate } from "./api/recommendations";
import { InteractiveMap } from "./components/InteractiveMap";
import { SimulatedReviews } from "./components/SimulatedReviews";
import "./index.css";

function PersonaSelector({ value, onChange }: { value: PersonaId; onChange: (persona: PersonaId) => void }) {
  return (
    <fieldset className="persona-fieldset">
      <legend>選擇一種體驗方式</legend>
      <div className="persona-grid">
        {personaOptions.map((persona) => (
          <label className={`persona-card ${value === persona.id ? "is-selected" : ""}`} key={persona.id}>
            <input checked={value === persona.id} name="persona" onChange={() => onChange(persona.id)} type="radio" value={persona.id} />
            <span>{persona.name}</span>
            <small>{persona.detail}</small>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function App() {
  const [flow, dispatch] = useReducer(demoFlowReducer, initialDemoFlowState);
  const [recommendation, setRecommendation] = useState<DemoRecommendation | null>(null);
  const [rideEstimate, setRideEstimate] = useState<RideEstimate | null>(null);
  const [manualLocation, setManualLocation] = useState<DemoLocation | null>(null);
  const [datetimeLocal, setDatetimeLocal] = useState(() => `${new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10)}T18:30`);
  const showTestLocations = typeof window !== "undefined" && new URLSearchParams(window.location.search).has("showTestLocations");
  const selectedLocation = useMemo(
    () => demoLocations.find((item) => item.id === flow.locationId) ?? demoLocations[0],
    [flow.locationId],
  );
  const location = manualLocation ?? selectedLocation;
  const requestDatetime = `${datetimeLocal}:00+08:00`;
  const selectedRestaurant = recommendation?.restaurants.find((restaurant) => restaurant.id === flow.selectedRestaurantId);

  useEffect(() => {
    if (flow.screen !== "RECOMMENDING") return;
    const timer = window.setTimeout(async () => {
      if (location.simulateError) {
        dispatch({ type: "RECOMMENDATION_FAILED", message: "目前找不到餐廳，請稍後再試或換個位置。" });
        return;
      }
      try {
        const apiRecommendation = await fetchRecommendation(location, flow.persona, requestDatetime);
        setRecommendation(apiRecommendation ?? buildDemoRecommendation(location, flow.persona));
      } catch {
        setRecommendation(buildDemoRecommendation(location, flow.persona));
      }
      dispatch({ type: "RECOMMENDATION_READY" });
    }, 420);
    return () => window.clearTimeout(timer);
  }, [flow.screen, flow.persona, location, requestDatetime]);

  useEffect(() => {
    if (flow.screen !== "RESULTS" || !recommendation) return;
    recommendation.restaurants.forEach((restaurant) => {
      void recordFeedback(recommendation.requestId, restaurant.id, "impression");
    });
  }, [flow.screen, recommendation]);

  useEffect(() => {
    if (flow.screen !== "RESTAURANT_DETAIL" || !recommendation || !selectedRestaurant) {
      setRideEstimate(null);
      return;
    }
    void recordFeedback(recommendation.requestId, selectedRestaurant.id, "explanation_opened");
    let active = true;
    void fetchRideEstimate(recommendation, location, selectedRestaurant, requestDatetime).then((estimate) => {
      if (active) setRideEstimate(estimate);
    });
    return () => { active = false; };
  }, [flow.screen, location, recommendation, requestDatetime, selectedRestaurant]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <button aria-label="返回首頁" className="brand-button" onClick={() => dispatch({ type: "BACK_HOME" })} type="button">
          <span className="brand-mark">Y</span><span>今天吃什麼</span>
        </button>
        <span className="demo-pill">非官方示範</span>
      </header>

      <InteractiveMap
        activeId={selectedRestaurant?.id}
        areas={recommendation?.calculation?.topAreas}
        encodedPolyline={rideEstimate?.encodedPolyline}
        onOriginChange={(coordinate) => {
          setManualLocation({ id: "map-selected", name: "你選的位置", detail: "在地圖上選取", fallback: false, ...coordinate });
          setRecommendation(null);
          dispatch({ type: "START" });
        }}
        onRestaurantSelect={(restaurantId) => {
          if (recommendation?.restaurants.some((restaurant) => restaurant.id === restaurantId)) {
            dispatch({ type: "OPEN_RESTAURANT", restaurantId });
          }
        }}
        origin={location}
        restaurants={recommendation?.restaurants ?? []}
      />

      <section className="bottom-sheet" aria-live="polite">
        <div className="sheet-handle" aria-hidden="true" />

        {flow.screen === "HOME" ? (
          <div className="screen home-screen">
            <p className="eyebrow">台北美食提案</p>
            <h1>今晚，換個方向吃飯</h1>
            <p className="summary">選好位置和時間，看看有哪些餐廳值得去。</p>
            <div className="location-preview">
              <span className="location-dot" />
              <div><strong>{location.name}</strong><small>可在下一步選擇時間與位置</small></div>
            </div>
            <button className="primary-button" onClick={() => dispatch({ type: "START" })} type="button">今天吃什麼</button>
          </div>
        ) : null}

        {flow.screen === "LOCATION_SELECTION" ? (
          <div className="screen">
            <p className="eyebrow">出發前</p><h2>先選好位置與時間</h2>
            <PersonaSelector onChange={(persona) => dispatch({ type: "SELECT_PERSONA", persona })} value={flow.persona} />
            <label className="select-label" htmlFor="location-select">目前位置</label>
            <select id="location-select" onChange={(event) => { setManualLocation(null); dispatch({ type: "SELECT_LOCATION", locationId: event.target.value }); }} value={flow.locationId}>
              {demoLocations.filter((item) => showTestLocations || !item.simulateError).map((item) => <option key={item.id} value={item.id}>{item.name} — {item.detail}</option>)}
            </select>
            <label className="select-label" htmlFor="datetime-select">出發時間</label>
            <input id="datetime-select" onChange={(event) => setDatetimeLocal(event.target.value)} type="datetime-local" value={datetimeLocal} />
            <p className="helper-text">如果地圖可以點選，也能直接在地圖上選擇出發位置。</p>
            <button className="primary-button" onClick={() => dispatch({ type: "RECOMMEND" })} type="button">找餐廳</button>
            <button className="secondary-button" onClick={() => dispatch({ type: "BACK_HOME" })} type="button">返回</button>
          </div>
        ) : null}

        {flow.screen === "RECOMMENDING" ? (
          <div className="screen loading-screen" role="status">
            <div className="loader" aria-hidden="true" />
            <p className="eyebrow">請稍候</p><h2>正在找適合的餐廳</h2>
            <p className="summary">為你看看附近有哪些選擇。</p>
          </div>
        ) : null}

        {flow.screen === "RESULTS" && recommendation ? (
          <div className="screen results-screen">
            <div className="result-heading">
              <div><p className="eyebrow">從 {location.name} 出發</p><h2>今晚推薦</h2></div>
              {recommendation.source !== "google_places" ? <span className="source-badge">示範餐廳</span> : null}
            </div>
            {location.fallback ? <p className="warning-banner">先看看台北其他地方的餐廳。</p> : null}
            {recommendation.source !== "google_places" ? <p className="data-warning">以下為示範餐廳，名稱與行程資訊僅供體驗。</p> : null}
            <ol className="restaurant-list">
              {recommendation.restaurants.map((restaurant) => (
                <li key={restaurant.id}>
                  <button className="restaurant-card" onClick={() => {
                    void recordFeedback(recommendation.requestId, restaurant.id, "restaurant_clicked");
                    dispatch({ type: "OPEN_RESTAURANT", restaurantId: restaurant.id });
                  }} type="button">
                    <span className="rank-number">{restaurant.rank}</span>
                    <span className="restaurant-copy"><strong>{restaurant.name}</strong><small>{restaurant.areaName} · {restaurant.distanceKm.toFixed(1)} km · 約 {restaurant.travelTimeMin} 分</small></span>
                    <span className="card-arrow" aria-hidden="true">›</span>
                  </button>
                </li>
              ))}
            </ol>
            <button className="secondary-button" onClick={() => dispatch({ type: "START" })} type="button">換個時間或位置</button>
          </div>
        ) : null}

        {flow.screen === "RESTAURANT_DETAIL" && selectedRestaurant && recommendation ? (
          <div className="screen detail-screen">
            <button className="back-button" onClick={() => dispatch({ type: "BACK_RESULTS" })} type="button">← 返回推薦</button>
            <p className="eyebrow">#{selectedRestaurant.rank} · {selectedRestaurant.areaName}</p><h2>{selectedRestaurant.name}</h2>
            {recommendation.source === "google_places" && selectedRestaurant.rating !== null ? <p className="review-summary">店家公開評分　★ {selectedRestaurant.rating.toFixed(1)}{selectedRestaurant.reviewCount !== null ? ` · ${selectedRestaurant.reviewCount} 則評價` : ""}</p> : null}
            <div className="detail-stats">
              <div><span>距離</span><strong>{selectedRestaurant.distanceKm.toFixed(1)} km</strong></div>
              <div><span>預估時間</span><strong>{selectedRestaurant.travelTimeMin} 分</strong></div>
              <div><span>營業資訊</span><strong>{recommendation.source === "google_places" && selectedRestaurant.openStatus === "open" ? "目前營業" : "請向店家確認"}</strong></div>
            </div>
            <div className="reason-card"><span>推薦原因</span><p>{selectedRestaurant.reason}</p></div>
            <SimulatedReviews key={selectedRestaurant.id} restaurant={selectedRestaurant} />
            <div className="fare-card">
              <span>參考車資</span>
              {rideEstimate?.fare ? (
                <><strong>NT$ {rideEstimate.fare.lower.toFixed(0)}–{rideEstimate.fare.upper.toFixed(0)}</strong><small>根據過往車資估算，實際金額請以正式報價為準。</small></>
              ) : <small>目前沒有可參考的車資。</small>}
            </div>
            <button className="primary-button" onClick={() => {
              void recordFeedback(recommendation.requestId, selectedRestaurant.id, "ride_clicked");
              dispatch({ type: "CONFIRM_RIDE" });
            }} type="button">預覽前往行程</button>
          </div>
        ) : null}

        {flow.screen === "RIDE_CONFIRMATION" && selectedRestaurant ? (
          <div className="screen confirmation-screen">
            <div className="success-icon" aria-hidden="true">✓</div><p className="eyebrow">行程預覽</p><h2>出發前先看看</h2>
            <p className="summary">前往 {selectedRestaurant.name}，預估約 {rideEstimate?.travelTimeMin ?? selectedRestaurant.travelTimeMin} 分鐘。這只是行程預覽，沒有叫車或產生費用。</p>
            <button className="primary-button" onClick={() => dispatch({ type: "BACK_HOME" })} type="button">回到首頁</button>
          </div>
        ) : null}

        {flow.screen === "ERROR" ? (
          <div className="screen error-screen" role="alert">
            <div className="error-icon" aria-hidden="true">!</div><p className="eyebrow">請再試一次</p><h2>暫時找不到餐廳</h2>
            <p className="summary">{flow.errorMessage}</p>
            <button className="primary-button" onClick={() => dispatch({ type: "RETRY" })} type="button">再試一次</button>
            <button className="secondary-button" onClick={() => dispatch({ type: "START" })} type="button">改選位置</button>
          </div>
        ) : null}
      </section>
    </main>
  );
}
