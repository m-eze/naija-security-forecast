export type RiskLevel = "LOW" | "MODERATE" | "HIGH" | "SEVERE";

// /api/risk/map
export interface LGAMapItem {
  id: string;
  name: string;
  state: string;
  score: number;
  level: RiskLevel;
  lng: number;
  lat: number;
}

export interface RiskMapResponse {
  score_date: string;
  total: number;
  lgas: LGAMapItem[];
}

// /api/risk/lga/{id}
export interface ComponentScores {
  frequency: number;
  trend: number;
  news: number;
}

export interface RiskComponents {
  incident_count_90d: number;
  fatalities_90d: number;
  incidents_last_30d: number;
  incidents_prior_30d: number;
  trend_direction: string;
  trend_ratio: number | null;
  news_articles_7d: number;
  avg_news_sentiment: number | null;
  dominant_event_types: string[];
  component_scores: ComponentScores;
}

export interface RiskScoreDetail {
  lga_id: string;
  lga_name: string;
  state: string;
  score: number;
  level: RiskLevel;
  score_date: string;
  incident_frequency_score: number;
  incident_trend_score: number;
  news_sentiment_score: number;
  components: RiskComponents;
  calculated_at: string;
}

// /api/risk/summary
export interface StateBreakdown {
  state: string;
  lga_count: number;
  severe: number;
  high: number;
  moderate: number;
  low: number;
  avg_score: number;
  max_score: number;
  top_lga: string;
  top_lga_score: number;
}

export interface NationalSummary {
  score_date: string;
  total_lgas: number;
  distribution: {
    SEVERE: number;
    HIGH: number;
    MODERATE: number;
    LOW: number;
  };
  states: StateBreakdown[];
  total_incidents_90d: number;
  total_fatalities_90d: number;
  security_news_7d: number;
}

// /api/news
export interface NewsArticle {
  id: string;
  headline: string;
  url: string;
  source: string;
  published_at: string;
  extracted_state: string | null;
  extracted_lga: string | null;
  sentiment_label: string;
  sentiment_score: number;
}

export interface PaginatedNews {
  total: number;
  page: number;
  page_size: number;
  items: NewsArticle[];
}

// /api/risk/geojson
export interface GeoJSONProperties {
  name: string;
  state: string;
  score: number | null;
  level: RiskLevel | null;
  frequency_score: number;
  trend_score: number;
  news_score: number;
}

export interface GeoJSONFeature {
  type: "Feature";
  id?: string; // LGA UUID
  geometry: object;
  properties: GeoJSONProperties;
}

export interface GeoJSONCollection {
  type: "FeatureCollection";
  features: GeoJSONFeature[];
}
