import { useState } from "react";
import type { DemoRestaurant } from "../mocks/taipeiDemo";

const reviewSnippets = [
  "這次用餐的整體感受不錯，會想把這個地方留作下次聚餐的候選。",
  "餐點選擇滿有彈性，適合先看看菜單再決定要點什麼。",
  "氣氛輕鬆，想找個地方好好吃頓飯時可以參考看看。",
  "同行的人都能找到想吃的品項，是一次舒服的用餐體驗。",
  "整體感覺很自在，想換個地方吃飯時會願意再考慮。",
];

interface SimulatedReviewsProps {
  restaurant: DemoRestaurant;
}

export function SimulatedReviews({ restaurant }: SimulatedReviewsProps) {
  const [myRating, setMyRating] = useState<number | null>(null);
  const seed = [...restaurant.id].reduce((sum, character) => sum + character.charCodeAt(0), 0);
  const reviews = [0, 1, 2].map((offset) => ({
    rating: [5, 4, 4][(seed + offset) % 3],
    text: reviewSnippets[(seed + offset) % reviewSnippets.length],
  }));
  const average = reviews.reduce((sum, review) => sum + review.rating, 0) / reviews.length;

  return (
    <section aria-labelledby="simulated-reviews-title" className="reviews-section">
      <div className="reviews-heading">
        <div>
          <p className="eyebrow">示意內容，非真實食客留言</p>
          <h3 id="simulated-reviews-title">模擬食客評論</h3>
        </div>
        <span className="review-average" aria-label={`模擬平均 ${average.toFixed(1)} 星`}>
          <span aria-hidden="true">★</span> {average.toFixed(1)}
        </span>
      </div>
      <ul className="simulated-review-list">
        {reviews.map((review, index) => (
          <li className="simulated-review" key={`${restaurant.id}-review-${index}`}>
            <div className="review-byline">
              <strong>示範食客 {String(index + 1).padStart(2, "0")}</strong>
              <span aria-label={`${review.rating} 星`} className="review-stars">{"★".repeat(review.rating)}{"☆".repeat(5 - review.rating)}</span>
            </div>
            <p>{review.text}</p>
          </li>
        ))}
      </ul>
      <div className="rate-demo">
        <strong>試著為這家店評分</strong>
        <div aria-label="選擇一到五顆星" className="rating-picker" role="group">
          {[1, 2, 3, 4, 5].map((rating) => (
            <button
              aria-label={`評 ${rating} 星`}
              aria-pressed={myRating === rating}
              className={myRating !== null && rating <= myRating ? "is-rated" : ""}
              key={rating}
              onClick={() => setMyRating(rating)}
              type="button"
            >★</button>
          ))}
        </div>
        <small role="status">{myRating === null ? "這是示範互動，不會送出或儲存評分。" : `你的示範評分：${myRating} 星（不會送出或儲存）`}</small>
      </div>
    </section>
  );
}
