"use client";

import { useEffect, useRef, useState } from "react";
import type { GeoJSONCollection, NewsPin } from "@/types";
import { scoreColor } from "@/lib/risk";
import LGADetailPanel from "./LGADetailPanel";

interface SelectedLGA {
  id: string;
  name: string;
  state: string;
}

interface Props {
  geojson: GeoJSONCollection;
  newsPins?: NewsPin[];
}

const PIN_COLOR: Record<string, string> = {
  negative: "#ef4444",
  neutral:  "#eab308",
  positive: "#22c55e",
};

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return "< 1h ago";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function NigeriaMap({ geojson, newsPins }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<import("leaflet").Map | null>(null);
  const pinsLayerRef = useRef<import("leaflet").LayerGroup | null>(null);
  const [selected, setSelected] = useState<SelectedLGA | null>(null);
  const [mapReady, setMapReady] = useState(false);

  // ── Init map + choropleth layer ──────────────────────────────────────────
  useEffect(() => {
    if (!mapRef.current) return;

    let cancelled = false;

    import("leaflet").then((L) => {
      if (cancelled || !mapRef.current || leafletMapRef.current) return;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;

      const map = L.map(mapRef.current, {
        center: [9.0, 8.0],
        zoom: 6,
        zoomControl: true,
        attributionControl: true,
      });

      L.tileLayer("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", {
        attribution:
          '© <a href="https://www.openstreetmap.org/copyright">OSM</a> © <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 19,
      }).addTo(map);

      L.tileLayer("https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png", {
        attribution: "",
        subdomains: "abcd",
        maxZoom: 19,
        pane: "overlayPane",
      }).addTo(map);

      let highlightedLayer: import("leaflet").Path | null = null;

      L.geoJSON(geojson as GeoJSON.FeatureCollection, {
        style: (feature) => ({
          fillColor: scoreColor(feature?.properties?.score ?? null),
          fillOpacity: 0.7,
          color: "#fff",
          weight: 0.5,
        }),
        onEachFeature: (feature, layer) => {
          const { name, state, score, level, incident_count } = feature.properties;
          const lgaId = (feature as { id?: string }).id;
          const isFilterMode = incident_count !== undefined;

          layer.on({
            mouseover: (e) => {
              const l = e.target as import("leaflet").Path;
              l.setStyle({ weight: 2, color: "#334155", fillOpacity: 0.9 });
              l.bringToFront();
            },
            mouseout: (e) => {
              const l = e.target as import("leaflet").Path;
              if (highlightedLayer !== l) {
                l.setStyle({ weight: 0.5, color: "#fff", fillOpacity: 0.7 });
              }
            },
            click: () => {
              if (highlightedLayer) {
                highlightedLayer.setStyle({ weight: 0.5, color: "#fff", fillOpacity: 0.7 });
              }
              const path = layer as import("leaflet").Path;
              path.setStyle({ weight: 2, color: "#0f172a", fillOpacity: 0.9 });
              highlightedLayer = path;
              if (lgaId && !isFilterMode) setSelected({ id: lgaId, name, state });
            },
          });

          const tooltipBody = isFilterMode
            ? incident_count > 0
              ? `${incident_count} incident${incident_count !== 1 ? "s" : ""}`
              : "No incidents"
            : score != null
            ? `${level ?? "—"} · ${score.toFixed(0)}/100`
            : "No data";

          layer.bindTooltip(
            `<strong>${name}</strong><br><span style="color:#64748b">${state}</span> &middot; ${tooltipBody}`,
            { sticky: true, className: "leaflet-tooltip-custom" }
          );
        },
      }).addTo(map);

      leafletMapRef.current = map;
      setMapReady(true);
    });

    return () => {
      cancelled = true;
      setMapReady(false);
      pinsLayerRef.current = null;
      if (leafletMapRef.current) {
        leafletMapRef.current.remove();
        leafletMapRef.current = null;
      }
    };
  }, [geojson]);

  // ── News pins layer — managed independently of the choropleth ────────────
  useEffect(() => {
    if (!mapReady || !leafletMapRef.current) return;

    // Remove previous pins layer
    if (pinsLayerRef.current) {
      pinsLayerRef.current.remove();
      pinsLayerRef.current = null;
    }

    if (!newsPins || newsPins.length === 0) return;

    import("leaflet").then((L) => {
      if (!leafletMapRef.current) return;

      const group = L.layerGroup();

      newsPins.forEach((pin) => {
        const color = PIN_COLOR[pin.sentiment_label] ?? PIN_COLOR.neutral;
        const location = [pin.lga, pin.state].filter(Boolean).join(", ");
        const ago = timeAgo(pin.published_at);

        L.circleMarker([pin.lat, pin.lng], {
          radius: 7,
          fillColor: color,
          color: "#fff",
          weight: 1.5,
          fillOpacity: 0.88,
          // Ensure pins render above the choropleth layer
          pane: "markerPane",
        })
          .bindPopup(
            `<div style="min-width:200px;max-width:260px">
              <div style="font-size:12px;font-weight:600;line-height:1.4;margin-bottom:4px">${pin.headline}</div>
              <div style="font-size:11px;color:#64748b;margin-bottom:6px">${pin.source} · ${location} · ${ago}</div>
              <a href="${pin.url}" target="_blank" rel="noopener noreferrer"
                 style="font-size:11px;color:#4f46e5;text-decoration:none">Read article →</a>
            </div>`,
            { maxWidth: 280 }
          )
          .addTo(group);
      });

      group.addTo(leafletMapRef.current);
      pinsLayerRef.current = group;
    });
  }, [newsPins, mapReady]);

  return (
    <div className="relative w-full h-full">
      <div ref={mapRef} className="w-full h-full" />

      {selected && (
        <LGADetailPanel
          lgaId={selected.id}
          lgaName={selected.name}
          state={selected.state}
          onClose={() => setSelected(null)}
        />
      )}

      <div className="absolute top-4 right-4 z-[1000] bg-white rounded-lg shadow-lg p-3 text-xs">
        <p className="font-semibold text-gray-600 mb-2 uppercase tracking-wide" style={{ fontSize: 10 }}>
          Risk Level
        </p>
        {[
          { label: "SEVERE (75–100)", color: "#ef4444" },
          { label: "HIGH (50–74)", color: "#f97316" },
          { label: "MODERATE (25–49)", color: "#eab308" },
          { label: "LOW (0–24)", color: "#22c55e" },
          { label: "No data", color: "#94a3b8" },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-2 mb-1">
            <span className="w-3 h-3 rounded-sm inline-block" style={{ backgroundColor: color }} />
            <span className="text-gray-600">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
