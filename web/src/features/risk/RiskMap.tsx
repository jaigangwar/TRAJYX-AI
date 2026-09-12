/**
 * MapLibre risk map.
 *
 * Layer order is deliberate: the basemap is desaturated, road segments are
 * drawn as risk-coloured lines, zones as translucent circles sized to their
 * real influence radius, and cameras as small markers on top. The risk colours
 * must be the brightest thing on screen — that is what the map is for.
 */

import {
  LngLatBounds,
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  type GeoJSONSource,
  type LngLatBoundsLike,
  type MapGeoJSONFeature,
  type MapMouseEvent,
} from "maplibre-gl";
import { useEffect, useRef } from "react";

import type { Camera } from "@/features/dashboard/api";
import type { RiskZone, RoadSegment } from "@/features/risk/api";
import { env } from "@/lib/env";
import { RISK_PRESENTATION } from "@/lib/risk";

import "maplibre-gl/dist/maplibre-gl.css";

interface RiskMapProps {
  segments: RoadSegment[];
  zones: RiskZone[];
  cameras: Camera[];
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string | null) => void;
  /** Click anywhere, for the alert-engine probe. */
  onProbe?: (latitude: number, longitude: number) => void;
  probePoint?: { latitude: number; longitude: number } | null;
}

/** The slice of GeoJSON this component actually produces. */
type Position = [number, number];
interface Feature {
  type: "Feature";
  id?: string;
  geometry:
    | { type: "Point"; coordinates: Position }
    | { type: "LineString"; coordinates: Position[] };
  properties: Record<string, unknown>;
}
interface FeatureCollection {
  type: "FeatureCollection";
  features: Feature[];
}

const SOURCE = {
  segments: "trajyx-segments",
  zones: "trajyx-zones",
  cameras: "trajyx-cameras",
  probe: "trajyx-probe",
};

/** Hex for a risk level, resolved from the CSS token at runtime. */
function riskColour(level: string | null | undefined): string {
  const fallback = "#6b7884";
  if (!level) return fallback;
  const token = RISK_PRESENTATION[level as keyof typeof RISK_PRESENTATION];
  if (!token) return fallback;
  // Tokens are `var(--color-…)`; MapLibre needs a literal, so resolve it.
  const name = token.color.match(/var\((--[^)]+)\)/)?.[1];
  if (!name) return token.color;
  const resolved = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return resolved || fallback;
}

export function RiskMap({
  segments,
  zones,
  cameras,
  selectedSegmentId,
  onSelectSegment,
  onProbe,
  probePoint,
}: RiskMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);

  /** Latest props, so the map can pull rather than be pushed to.
   *
   *  MapLibre rejects `setData` before the style loads, and React gives no
   *  ordering guarantee between the data arriving and the load event firing.
   *  An earlier version queued callbacks instead, and under StrictMode's
   *  double-mount the queue held closures bound to an already-removed map, so
   *  nothing was ever drawn. Holding the data in a ref and letting both the
   *  load handler and the data effect call one sync function removes the
   *  ordering problem entirely. */
  const dataRef = useRef({ segments, zones, cameras, selectedSegmentId, probePoint });
  const syncRef = useRef<() => void>(() => undefined);
  const fittedRef = useRef(false);

  // --- create the map once -------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new MapLibreMap({
      container: containerRef.current,
      style: env.VITE_MAP_STYLE_URL,
      center: [77.15, 28.53],
      zoom: 10.5,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    // Exposed in development so the map can be inspected from the console
    // and from the screenshot harness. Never referenced by product code.
    if (import.meta.env.DEV) {
      (window as unknown as { __trajyxMap?: MapLibreMap }).__trajyxMap = map;
    }

    /** Push the current ref contents into the map sources. */
    const sync = () => {
      const { segments: currentSegments, zones: currentZones, cameras: currentCameras, selectedSegmentId: currentSelected, probePoint: currentProbe } = dataRef.current;

      const segmentSource = map.getSource(SOURCE.segments) as GeoJSONSource | undefined;
      const zoneSource = map.getSource(SOURCE.zones) as GeoJSONSource | undefined;
      const cameraSource = map.getSource(SOURCE.cameras) as GeoJSONSource | undefined;
      const probeSource = map.getSource(SOURCE.probe) as GeoJSONSource | undefined;
      if (!segmentSource || !zoneSource || !cameraSource || !probeSource) return;

      const segmentData: FeatureCollection = {
        type: "FeatureCollection",
        features: currentSegments
          .filter((segment) => segment.path.length >= 2)
          .map((segment) => ({
            type: "Feature" as const,
            id: segment.id,
            geometry: {
              type: "LineString" as const,
              coordinates: segment.path.map(
                (point) => [point.longitude, point.latitude] as Position,
              ),
            },
            properties: {
              id: segment.id,
              name: segment.name,
              colour: riskColour(segment.risk_level),
              scored: segment.risk_score !== null && segment.risk_score !== undefined,
              selected: segment.id === currentSelected,
            },
          })),
      };
      segmentSource.setData(segmentData as never);

      const zoneData: FeatureCollection = {
        type: "FeatureCollection",
        features: currentZones.map((zone) => ({
          type: "Feature" as const,
          geometry: {
            type: "Point" as const,
            coordinates: [zone.centre.longitude, zone.centre.latitude] as Position,
          },
          properties: {
            id: zone.id,
            radius_m: zone.radius_m,
            colour: riskColour(zone.risk_level),
            score: zone.risk_score,
          },
        })),
      };
      zoneSource.setData(zoneData as never);

      const cameraData: FeatureCollection = {
        type: "FeatureCollection",
        features: currentCameras.map((camera) => ({
          type: "Feature" as const,
          geometry: {
            type: "Point" as const,
            coordinates: [camera.location.longitude, camera.location.latitude] as Position,
          },
          properties: {
            id: camera.id,
            name: camera.name,
            colour: camera.status === "ALERT" ? riskColour("CRITICAL") : "#9aa7b2",
          },
        })),
      };
      cameraSource.setData(cameraData as never);

      const probeData: FeatureCollection = {
        type: "FeatureCollection",
        features: currentProbe
          ? [
              {
                type: "Feature" as const,
                geometry: {
                  type: "Point" as const,
                  coordinates: [currentProbe.longitude, currentProbe.latitude] as Position,
                },
                properties: {},
              },
            ]
          : [],
      };
      probeSource.setData(probeData as never);
    };
    /** Zoom to the segments once, the first time any arrive. */
    const fitToData = () => {
      if (fittedRef.current) return;
      const coordinates = dataRef.current.segments.flatMap((segment) =>
        segment.path.map((point) => [point.longitude, point.latitude] as [number, number]),
      );
      if (coordinates.length === 0) return;

      const bounds = coordinates.reduce(
        (accumulator, coordinate) => accumulator.extend(coordinate),
        new LngLatBounds(coordinates[0]!, coordinates[0]!),
      );
      map.fitBounds(bounds as LngLatBoundsLike, { padding: 90, maxZoom: 15, duration: 0 });
      fittedRef.current = true;
    };

    // One entry point for both callers. The load handler runs it when the
    // layers first exist; the data effect runs it whenever props change.
    // Fitting is folded in here because the first sync that carries segments
    // may well be the one after load, not load itself.
    syncRef.current = () => {
      sync();
      fitToData();
    };

    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");

    map.on("load", () => {
      // Empty sources up front so the layers exist before data arrives; adding
      // layers later would fight with React's render timing.
      for (const id of Object.values(SOURCE)) {
        map.addSource(id, { type: "geojson", data: emptyCollection() });
      }

      map.addLayer({
        id: "zone-fill",
        type: "circle",
        source: SOURCE.zones,
        paint: {
          // Radius scales with zoom so the circle keeps its real ground size,
          // but never falls below 7px: a 140 m zone is sub-pixel at city
          // zoom, and an invisible risk zone is the same as no risk zone.
          // `zoom` must be the top-level input to interpolate, so the
          // minimum is applied inside each stop rather than around the whole
          // expression.
          "circle-radius": [
            "interpolate",
            ["exponential", 2],
            ["zoom"],
            10,
            ["max", 7, ["/", ["get", "radius_m"], 60]],
            16,
            ["max", 7, ["/", ["get", "radius_m"], 1.2]],
          ],
          "circle-color": ["get", "colour"],
          "circle-opacity": 0.22,
          "circle-stroke-color": ["get", "colour"],
          "circle-stroke-width": 2,
          "circle-stroke-opacity": 0.9,
        },
      });

      map.addLayer({
        id: "segment-line",
        type: "line",
        source: SOURCE.segments,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["get", "colour"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 9, ["case", ["get", "selected"], 5, 3], 14, ["case", ["get", "selected"], 9, 5]],
          "line-opacity": ["case", ["get", "scored"], 0.95, 0.4],
        },
      });

      map.addLayer({
        id: "segment-hit",
        type: "line",
        source: SOURCE.segments,
        paint: { "line-color": "#000000", "line-opacity": 0, "line-width": 18 },
      });

      map.addLayer({
        id: "camera-point",
        type: "circle",
        source: SOURCE.cameras,
        paint: {
          "circle-radius": 5,
          "circle-color": ["get", "colour"],
          "circle-stroke-color": "#0a0e11",
          "circle-stroke-width": 1.5,
        },
      });

      map.addLayer({
        id: "probe-point",
        type: "circle",
        source: SOURCE.probe,
        paint: {
          "circle-radius": 7,
          "circle-color": "#14b8a1",
          "circle-stroke-color": "#0a0e11",
          "circle-stroke-width": 2,
        },
      });

      syncRef.current();
      fitToData();
    });

    map.on(
      "click",
      "segment-hit",
      (event: MapMouseEvent & { features?: MapGeoJSONFeature[] }) => {
        const id = event.features?.[0]?.properties?.id;
        if (typeof id === "string") {
          onSelectSegment(id);
          event.originalEvent.stopPropagation();
        }
      },
    );

    map.on("click", (event: MapMouseEvent) => {
      // A click that did not land on a segment is a probe of the alert engine.
      const hits = map.queryRenderedFeatures(event.point, { layers: ["segment-hit"] });
      if (hits.length === 0) onProbe?.(event.lngLat.lat, event.lngLat.lng);
    });

    for (const layer of ["segment-hit", "camera-point"]) {
      map.on("mouseenter", layer, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
      });
    }

    return () => {
      syncRef.current = () => undefined;
      fittedRef.current = false;
      map.remove();
      mapRef.current = null;
    };
    // Handlers are stable enough in practice and re-creating the map on every
    // render would be far worse than a slightly stale closure.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- keep the ref current and re-sync ----------------------------------
  useEffect(() => {
    dataRef.current = { segments, zones, cameras, selectedSegmentId, probePoint };
    syncRef.current();
  }, [segments, zones, cameras, selectedSegmentId, probePoint]);

  return <div ref={containerRef} className="bg-surface-sunken h-full w-full" />;
}

function emptyCollection(): FeatureCollection {
  return { type: "FeatureCollection", features: [] };
}
