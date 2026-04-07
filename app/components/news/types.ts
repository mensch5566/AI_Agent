export interface NewsItem {
  id?: string;
  date: string;
  headline: string;
  summary: string;
  analysis?: string;
  url?: string;
  ticker?: string;
  sentiment?: "bullish" | "bearish" | "neutral";
}

export interface FeedbackTarget {
  index: number;
  headline: string;
  url?: string;
  ticker?: string;
  sentiment?: string;
}
