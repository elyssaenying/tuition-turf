import { useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MapLibreMap, MapLayerMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type Station = {
  id: string;
  name: string;
  planningArea: string;
  region: string;
  population800m: number;
  population1200m: number;
  rank: number;
  percentile: number;
  busStops800m: number;
  schools800m: number;
  accessibilityPopulation: number;
  accessibilityRank: number;
  ptAccessiblePopulation: number;
  walkingAccessiblePopulation: number;
  proximityFallbackPopulation: number;
  transitReachShare: number;
  longitude: number;
  latitude: number;
};

type Metric = "accessibility" | "proximity";

type H2Result = {
  materialDifference: boolean;
  medianDifference: number;
  rankCorrelation: number;
  movedTenRanks: number;
  validNodeCount: number;
};

type Recommendation = {
  commercial_node_id: string;
  display_name: string;
  planning_region: string;
  recommendation_rank: number;
  nearby_population_proxy_800m: number;
  primary_accessible_population_proxy: number;
  confirmed_competitors_10_min: number;
  confirmed_competitors_15_min: number;
  possible_competitors_10_min: null;
  possible_count_status: string;
  selection_count: number;
  top_three_frequency: number;
  top_three_frequency_zero_confirmed_caution: number;
  pareto_frequency: number;
  median_rank: number;
  worst_rank: number;
  rationale: string;
  next_due_diligence: string;
};

type FinalAnalysis = {
  competition: {
    coverage: {
      fixed_queries_completed: number;
      fixed_queries_planned: number;
      unique_mrt_areas: number;
      unique_confirmed_physical_branches: number;
      walking_routes_completed: number;
    };
    h1: {
      direction_observed: boolean;
      inferential_status: string;
      primary_design_weighted_result: { weighted_correlation: number };
      interpretation: string;
    };
  };
  decision: {
    method: {
      profile_ranking_evaluations: number;
      unique_rank_orderings: number;
      location_sensitivity_scenarios: number;
      illustrative_finance_case_evaluations: number;
    };
    financial_scenarios: Array<{
      scenario_id: string;
      occupancy_cost: number;
      non_occupancy_fixed_cost: number;
      effective_fee_per_student: number;
      variable_cost_per_student: number;
      contribution_per_student: number;
      break_even_active_enrolments: number;
      break_even_utilisation: number;
    }>;
    recommendations: Recommendation[];
    claim_boundary: string;
  };
};

type TravelTimeSensitivity = {
  comparison_scope: "same_original_36_mrt_areas";
  walking_fallback_minutes: number;
  straight_line_fallback_metres: number;
  comparisons_per_limit: number;
  thresholds: Array<{
    public_transport_minutes: number;
    candidate_screen_overlap_with_20_minutes: number;
    top_three_counts: { SENGKANG: number; SERANGOON: number };
  }>;
};

type GeoFeature = {
  geometry: { coordinates: [number, number] };
  properties: { commercial_node_id: string };
};

type BoundaryFeature = {
  properties: {
    region_name: string;
  };
  geometry: {
    type: "Polygon" | "MultiPolygon";
    coordinates: number[][][] | number[][][][];
  };
};

const number = new Intl.NumberFormat("en-SG", { maximumFractionDigits: 0 });
const REGION_STYLES = [
  { key: "central", value: "CENTRAL REGION", label: "Central", color: "#6b4fc1", tint: "#ebe6f7" },
  { key: "east", value: "EAST REGION", label: "East", color: "#c4513a", tint: "#f5e3dc" },
  { key: "north", value: "NORTH REGION", label: "North", color: "#167466", tint: "#dcece7" },
  { key: "northEast", value: "NORTH-EAST REGION", label: "North-East", color: "#316e8c", tint: "#dfeaf0" },
  { key: "west", value: "WEST REGION", label: "West", color: "#9b6f10", tint: "#f1e9d3" },
] as const;

function regionColor(regionName: string) {
  return REGION_STYLES.find((region) => region.value === regionName)?.color ?? "#6f817a";
}

function parseCsv(input: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;

  for (let index = 0; index < input.length; index += 1) {
    const character = input[index];
    if (character === '"') {
      if (quoted && input[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && input[index + 1] === "\n") index += 1;
      row.push(cell);
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += character;
    }
  }

  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

function cleanStationName(name: string) {
  return name.replace(/ MRT STATION$/i, "").replace(/ LRT STATION$/i, "");
}

function rankMovementLabel(station: Station) {
  const movement = station.rank - station.accessibilityRank;
  if (movement === 0) return "same position as the 800 m map estimate";
  return `${movement > 0 ? "rose" : "fell"} ${Math.abs(movement)} position${Math.abs(movement) === 1 ? "" : "s"} compared with the 800 m map estimate`;
}

function recommendationInterpretation(item: Recommendation, sensitivity: TravelTimeSensitivity | null) {
  if (item.display_name === "SENGKANG") {
    return `I would investigate Sengkang first. It stayed in the top three whenever the tested assumptions changed${sensitivity ? ", including all three travel limits" : ""}. This is the stronger result, but it does not tell us whether a particular unit is affordable or suitable.`;
  }
  if (item.display_name === "SERANGOON") {
    return `Serangoon stays on the published shortlist, but I would treat it as an area to investigate further, not an equally strong recommendation.${sensitivity ? " It placed in the top three only when the model allowed a 25-minute public-transport trip, not at 15 or 20 minutes." : " Its result depends more heavily on the travel-time assumption."} That does not show how long families are actually willing to travel.`;
  }
  return item.rationale;
}

function travelResultLabel(count: number, total: number) {
  if (count === total) return "In the top three every time";
  if (count === 0) return "Outside the top three in every comparison";
  if (count > total / 2) return "In the top three most of the time";
  return "In the top three some of the time";
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M4 10h11M11 6l4 4-4 4" />
    </svg>
  );
}

function StageIcon({ state }: { state: "done" | "active" | "pending" }) {
  return <span className={`stage-icon ${state}`}>{state === "done" ? "✓" : state === "active" ? "↗" : "·"}</span>;
}

export default function App() {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const selectedMapFeatureRef = useRef<string | null>(null);
  const [stations, setStations] = useState<Station[]>([]);
  const [boundaries, setBoundaries] = useState<BoundaryFeature[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [region, setRegion] = useState("All regions");
  const [query, setQuery] = useState("");
  const [mapScope, setMapScope] = useState<"leaders" | "all">("all");
  const [metric, setMetric] = useState<Metric>("accessibility");
  const [h2, setH2] = useState<H2Result | null>(null);
  const [finalAnalysis, setFinalAnalysis] = useState<FinalAnalysis | null>(null);
  const [travelSensitivity, setTravelSensitivity] = useState<TravelTimeSensitivity | null>(null);
  const [loadingError, setLoadingError] = useState("");

  useEffect(() => {
    if (!stations.length || !window.location.hash) return;
    const sectionId = window.location.hash.slice(1);
    const timer = window.setTimeout(() => document.getElementById(sectionId)?.scrollIntoView(), 0);
    return () => window.clearTimeout(timer);
  }, [stations.length]);

  useEffect(() => {
    Promise.all([
      fetch("/data/node_proximity_metrics.csv").then((response) => response.text()),
      fetch("/data/node_accessibility_metrics.csv").then((response) => response.text()),
      fetch("/data/h2-results.json").then((response) => response.json()),
      fetch("/data/node_inspection.geojson").then((response) => response.json()),
      fetch("/data/mp2019_subzones.geojson").then((response) => response.json()),
      fetch("/data/final-analysis.json").then((response) => response.json()),
      fetch("/data/travel-time-sensitivity.json").then((response) => response.json()),
    ])
      .then(([csv, accessibilityCsv, h2Result, geojson, subzoneGeojson, completedAnalysis, sensitivity]) => {
        const rows = parseCsv(csv);
        const headers = rows[0];
        const column = (name: string) => headers.indexOf(name);
        const accessibilityRows = parseCsv(accessibilityCsv);
        const accessibilityHeaders = accessibilityRows[0];
        const accessibilityColumn = (name: string) => accessibilityHeaders.indexOf(name);
        const primaryAccessibility = accessibilityRows
          .slice(1)
          .filter(
            (row) =>
              row[accessibilityColumn("scenario_id")] === "primary_weekday_after_school" &&
              row[accessibilityColumn("is_primary_threshold_case")] === "True",
          );
        const accessibilityRanks = new Map(
          [...primaryAccessibility]
            .sort(
              (left, right) =>
                Number(right[accessibilityColumn("accessible_target_population_proxy")]) -
                  Number(left[accessibilityColumn("accessible_target_population_proxy")]) ||
                left[accessibilityColumn("commercial_node_id")].localeCompare(
                  right[accessibilityColumn("commercial_node_id")],
                ),
            )
            .map((row, index) => [row[accessibilityColumn("commercial_node_id")], index + 1]),
        );
        const accessibilityById = new Map(
          primaryAccessibility.map((row) => [row[accessibilityColumn("commercial_node_id")], row]),
        );
        const coordinates = new Map<string, [number, number]>(
          (geojson.features as GeoFeature[]).map((feature) => [
            feature.properties.commercial_node_id,
            feature.geometry.coordinates,
          ]),
        );
        const loaded = rows.slice(1).map((row) => {
          const id = row[column("commercial_node_id")];
          const point = coordinates.get(id) ?? [103.82, 1.35];
          const accessibility = accessibilityById.get(id);
          return {
            id,
            name: cleanStationName(row[column("node_name")]),
            planningArea: row[column("planning_area_name_at_anchor")],
            region: row[column("region_name_at_anchor")],
            population800m: Number(row[column("proximity_target_population_proxy_800m")]),
            population1200m: Number(row[column("proximity_target_population_proxy_1200m")]),
            rank: Number(row[column("population_proxy_800m_rank")]),
            percentile: Number(row[column("population_proxy_800m_percentile")]),
            busStops800m: Number(row[column("bus_stop_count_800m")]),
            schools800m: Number(row[column("school_context_count_800m")]),
            accessibilityPopulation: Number(
              accessibility?.[accessibilityColumn("accessible_target_population_proxy")] ?? 0,
            ),
            accessibilityRank: accessibilityRanks.get(id) ?? 146,
            ptAccessiblePopulation: Number(
              accessibility?.[accessibilityColumn("pt_accessible_population_proxy")] ?? 0,
            ),
            walkingAccessiblePopulation: Number(
              accessibility?.[accessibilityColumn("walking_fallback_accessible_population_proxy")] ?? 0,
            ),
            proximityFallbackPopulation: Number(
              accessibility?.[accessibilityColumn("proximity_fallback_accessible_population_proxy")] ?? 0,
            ),
            transitReachShare: Number(accessibility?.[accessibilityColumn("transit_reach_share")] ?? 0),
            longitude: point[0],
            latitude: point[1],
          };
        });
        loaded.sort((a, b) => a.accessibilityRank - b.accessibilityRank);
        setStations(loaded);
        setBoundaries(subzoneGeojson.features as BoundaryFeature[]);
        setSelectedId(loaded[0]?.id ?? "");
        setH2({
          materialDifference: Boolean(h2Result.material_difference),
          medianDifference: Number(h2Result.median_node_absolute_percentage_difference),
          rankCorrelation: Number(h2Result.spearman_rank_correlation),
          movedTenRanks: Number(h2Result.nodes_moving_at_least_10_ranks_count),
          validNodeCount: Number(h2Result.valid_node_count),
        });
        setFinalAnalysis(completedAnalysis as FinalAnalysis);
        setTravelSensitivity(sensitivity as TravelTimeSensitivity);
      })
      .catch(() => setLoadingError("The local dashboard data could not be loaded."));
  }, []);

  const regions = useMemo(
    () => ["All regions", ...Array.from(new Set(stations.map((station) => station.region))).sort()],
    [stations],
  );

  const filteredStations = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return stations
      .filter(
        (station) =>
          (region === "All regions" || station.region === region) &&
          (!normalizedQuery ||
            station.name.toLowerCase().includes(normalizedQuery) ||
            station.planningArea.toLowerCase().includes(normalizedQuery)),
      )
      .sort((left, right) =>
        metric === "accessibility"
          ? left.accessibilityRank - right.accessibilityRank
          : left.rank - right.rank,
      );
  }, [stations, region, query, metric]);

  const selected = stations.find((station) => station.id === selectedId) ?? stations[0];
  const stationRank = (station: Station) => metric === "accessibility" ? station.accessibilityRank : station.rank;
  const stationValue = (station: Station) => metric === "accessibility" ? station.accessibilityPopulation : station.population800m;
  const maxPopulation = Math.max(...stations.map(stationValue), 1);
  const mappedStations = useMemo(() => {
    if (mapScope === "all") return filteredStations;
    return filteredStations.filter((station) => stationRank(station) <= 10 || station.id === selected?.id);
  }, [filteredStations, mapScope, selected?.id, metric]);

  const stationFeatureCollection = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: mappedStations.map((station) => ({
        type: "Feature" as const,
        id: station.id,
        geometry: { type: "Point" as const, coordinates: [station.longitude, station.latitude] },
        properties: {
          id: station.id,
          name: station.name,
          region: station.region,
          rank: stationRank(station),
          population: Math.round(stationValue(station)),
          score: stationValue(station) / maxPopulation,
        },
      })),
    }),
    [mappedStations, metric, maxPopulation],
  );

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current || !stations.length || !boundaries.length) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: "background", type: "background", paint: { "background-color": "#e8efeb" } }],
      },
      center: [103.82, 1.35],
      zoom: 10.25,
      minZoom: 9.6,
      maxZoom: 15.5,
      attributionControl: false,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: "map-data-popup" });
    const clusterCountMarkers = new Map<number, maplibregl.Marker>();
    const setPointer = () => { map.getCanvas().style.cursor = "pointer"; };
    const clearPointer = () => { map.getCanvas().style.cursor = ""; popup.remove(); };

    const updateClusterCountMarkers = () => {
      if (!map.getSource("stations") || !map.getLayer("station-clusters")) return;

      const visibleClusterIds = new Set<number>();
      for (const feature of map.queryRenderedFeatures({ layers: ["station-clusters"] })) {
        const clusterId = Number(feature.properties?.cluster_id);
        const count = Number(feature.properties?.point_count);
        if (!feature.properties?.cluster || !Number.isFinite(clusterId) || feature.geometry.type !== "Point") continue;

        visibleClusterIds.add(clusterId);
        const regionCounts = REGION_STYLES.map((regionStyle) => Number(feature.properties?.[regionStyle.key] ?? 0));
        let runningCount = 0;
        const segments = REGION_STYLES.flatMap((regionStyle, index) => {
          const start = (runningCount / count) * 360;
          runningCount += regionCounts[index];
          const end = (runningCount / count) * 360;
          return regionCounts[index] > 0 ? [`${regionStyle.color} ${start}deg ${end}deg`] : [];
        });

        let marker = clusterCountMarkers.get(clusterId);
        if (!marker) {
          const markerElement = document.createElement("div");
          const countLabel = document.createElement("span");
          markerElement.className = "map-cluster-count";
          markerElement.append(countLabel);
          markerElement.setAttribute("aria-hidden", "true");
          marker = new maplibregl.Marker({ element: markerElement, anchor: "center" })
            .setLngLat(feature.geometry.coordinates as [number, number])
            .addTo(map);
          clusterCountMarkers.set(clusterId, marker);
        }

        const markerElement = marker.getElement();
        const size = count >= 24 ? 44 : count >= 10 ? 36 : count >= 4 ? 29 : 23;
        markerElement.style.setProperty("--cluster-size", `${size}px`);
        markerElement.style.setProperty("--cluster-ring", segments.length ? `conic-gradient(${segments.join(",")})` : "#155f56");
        const countLabel = markerElement.querySelector("span");
        if (countLabel) countLabel.textContent = String(feature.properties?.point_count_abbreviated ?? count);
        marker.setLngLat(feature.geometry.coordinates as [number, number]);
      }

      for (const [clusterId, marker] of clusterCountMarkers) {
        if (!visibleClusterIds.has(clusterId)) {
          marker.remove();
          clusterCountMarkers.delete(clusterId);
        }
      }
    };

    map.on("load", () => {
      map.addSource("subzones", {
        type: "geojson",
        data: { type: "FeatureCollection", features: boundaries } as never,
      });
      map.addLayer({
        id: "subzone-fill",
        type: "fill",
        source: "subzones",
        paint: {
          "fill-color": [
            "match",
            ["get", "region_name"],
            ...REGION_STYLES.flatMap((region) => [region.value, region.tint]),
            "#e4ebe7",
          ] as never,
          "fill-opacity": 0.72,
        },
      });
      map.addLayer({
        id: "subzone-lines",
        type: "line",
        source: "subzones",
        paint: { "line-color": "#afc0b8", "line-width": 0.65, "line-opacity": 0.8 },
      });
      map.addSource("stations", {
        type: "geojson",
        data: stationFeatureCollection,
        cluster: true,
        clusterMaxZoom: 13,
        clusterRadius: 34,
        clusterProperties: Object.fromEntries(
          REGION_STYLES.map((region) => [
            region.key,
            ["+", ["case", ["==", ["get", "region"], region.value], 1, 0]],
          ]),
        ),
      });
      map.addLayer({
        id: "station-clusters",
        type: "circle",
        source: "stations",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#155f56",
          "circle-opacity": 0.9,
          "circle-radius": ["step", ["get", "point_count"], 10, 4, 13, 10, 17, 24, 21],
          "circle-stroke-color": "#f8f5ed",
          "circle-stroke-width": 2,
        },
      });
      map.addLayer({
        id: "station-points",
        type: "circle",
        source: "stations",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            "#17211f",
            [
              "match",
              ["get", "region"],
              ...REGION_STYLES.flatMap((region) => [region.value, region.color]),
              "#6f817a",
            ],
          ] as never,
          "circle-radius": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            7,
            ["interpolate", ["linear"], ["get", "score"], 0, 3.2, 1, 5.8],
          ],
          "circle-stroke-color": ["case", ["boolean", ["feature-state", "selected"], false], "#f06c4f", "#fffdf7"],
          "circle-stroke-width": ["case", ["boolean", ["feature-state", "selected"], false], 3, 1.4],
        },
      });

      map.on("render", updateClusterCountMarkers);
      updateClusterCountMarkers();

      map.on("click", "station-clusters", (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0];
        const clusterId = Number(feature?.properties?.cluster_id);
        if (feature?.geometry.type !== "Point") return;
        const coordinates = feature.geometry.coordinates as [number, number];
        const source = map.getSource("stations") as GeoJSONSource;
        if (!Number.isFinite(clusterId)) return;
        source.getClusterExpansionZoom(clusterId).then((zoom) => {
          map.easeTo({ center: coordinates, zoom, duration: 550 });
        });
      });
      map.on("click", "station-points", (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0];
        if (feature?.properties?.id) setSelectedId(String(feature.properties.id));
      });
      map.on("mouseenter", "station-clusters", (event: MapLayerMouseEvent) => {
        setPointer();
        const feature = event.features?.[0];
        if (feature?.geometry.type !== "Point") return;
        const coordinates = feature.geometry.coordinates as [number, number];
        const label = document.createElement("div");
        label.textContent = `${feature?.properties?.point_count ?? "Several"} MRT areas · click to expand`;
        popup.setLngLat(coordinates).setDOMContent(label).addTo(map);
      });
      map.on("mouseenter", "station-points", (event: MapLayerMouseEvent) => {
        setPointer();
        const feature = event.features?.[0];
        if (feature?.geometry.type !== "Point") return;
        const coordinates = feature.geometry.coordinates as [number, number];
        const label = document.createElement("div");
        const name = document.createElement("strong");
        const detail = document.createElement("span");
        name.textContent = String(feature?.properties?.name ?? "MRT area");
        detail.textContent = `Position ${feature?.properties?.rank} · ${number.format(Number(feature?.properties?.population ?? 0))}`;
        label.append(name, detail);
        popup.setLngLat(coordinates).setDOMContent(label).addTo(map);
      });
      map.on("mouseleave", "station-clusters", clearPointer);
      map.on("mouseleave", "station-points", clearPointer);

      map.fitBounds([[103.59, 1.14], [104.07, 1.49]], { padding: 20, duration: 0 });
      if (selectedId) {
        map.setFeatureState({ source: "stations", id: selectedId }, { selected: true });
        selectedMapFeatureRef.current = selectedId;
      }
    });

    return () => {
      map.off("render", updateClusterCountMarkers);
      for (const marker of clusterCountMarkers.values()) marker.remove();
      popup.remove();
      map.remove();
      mapRef.current = null;
    };
  }, [boundaries.length, stations.length]);

  useEffect(() => {
    const source = mapRef.current?.getSource("stations") as GeoJSONSource | undefined;
    if (source) source.setData(stationFeatureCollection);
  }, [stationFeatureCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !selected) return;
    if (selectedMapFeatureRef.current) {
      map.setFeatureState({ source: "stations", id: selectedMapFeatureRef.current }, { selected: false });
    }
    map.setFeatureState({ source: "stations", id: selected.id }, { selected: true });
    selectedMapFeatureRef.current = selected.id;
    map.easeTo({ center: [selected.longitude, selected.latitude], zoom: Math.max(map.getZoom(), 13.15), duration: 650 });
  }, [selected?.id]);

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="Tuition Location Intelligence home">
          <span className="brand-mark"><i /><i /><i /></span>
          <span>Tuition Location Intelligence</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#explore">Explore</a>
          <a href="#recommendations">Results</a>
          <a href="#method">Method</a>
        </nav>
        <a className="header-action" href="#explore">View analysis <ArrowIcon /></a>
      </header>

      <main id="top">
        <section className="hero">
          <div className="hero-grid" aria-hidden="true" />
          <svg className="hero-network" viewBox="0 0 800 520" aria-hidden="true">
            <path d="M60 380C210 320 238 395 360 280S590 215 760 88" />
            <path d="M96 96C250 140 320 84 430 200s206 156 330 148" />
            <path d="M230 480c34-135 104-178 205-194 142-22 176-102 200-215" />
            {[80, 180, 290, 405, 515, 630, 735].map((x, index) => (
              <circle key={x} cx={x} cy={[373, 335, 340, 252, 230, 171, 105][index]} r={index === 3 ? 8 : 5} />
            ))}
          </svg>
          <div className="eyebrow"><span>Portfolio case study</span><span>Singapore · P1–S4 Mathematics</span></div>
          <div className="hero-copy">
            <p className="kicker">An evidence-led location decision</p>
            <h1>Where should a tuition centre open?</h1>
            <p className="hero-intro">
              I wanted to understand how many school-age residents live near an area, how easily they can reach it,
              and which tuition centres already operate nearby. This dashboard brings those factors
              into a transparent shortlist for operators to investigate. It is not a guarantee of success.
            </p>
            <div className="hero-actions">
              <a className="primary-button" href="#explore">Explore the analysis <ArrowIcon /></a>
              <a className="text-link" href="#method">See how it works</a>
            </div>
          </div>
          <div className="hero-metrics" aria-label="Project summary">
            <div><strong>146</strong><span>MRT areas screened</span></div>
            <div><strong>332</strong><span>Residential areas modelled</span></div>
            <div><strong>36</strong><span>Areas compared in detail</span></div>
            <div className="status-metric"><strong>2</strong><span><b /> areas for further investigation</span></div>
          </div>
        </section>

        <section className="status-strip" aria-label="Dashboard status">
          <span className="live-dot" />
          <strong>Analysis complete</strong>
          <span>146 MRT areas screened · 36 candidates compared · 40 extra areas checked · quality checks passed</span>
          <span className="status-date">Original analysis: 18 Sep · travel-time check: 28 Sep 2026</span>
        </section>

        <section className="quick-start" aria-labelledby="quick-start-title">
          <div className="quick-start-heading">
            <p className="section-number">Start here</p>
            <h2 id="quick-start-title">What the analysis found</h2>
            <p>Use this as an area-screening guide. An “MRT area” means the station and its immediate surroundings. The analysis identifies where further investigation should begin, not which unit to lease.</p>
          </div>
          <div className="quick-start-grid">
            <article>
              <span>Strongest result</span>
              <strong>Sengkang</strong>
              <p>It stayed near the top across every tested set of assumptions. Investigate this area first.</p>
            </article>
            <article>
              <span>Depends on travel time</span>
              <strong>Serangoon</strong>
              <p>It ranked near the top only when the model allowed 25 minutes by public transport. Treat it as a less certain option.</p>
            </article>
            <article>
              <span>Still required</span>
              <strong>Check an actual unit</strong>
              <p>Current rent, available spaces, people passing by and local parent interest were not measured.</p>
            </article>
          </div>
        </section>

        <nav className="reading-path" aria-label="Follow the analysis">
          <a href="#explore"><span>1</span><strong>Explore population and travel</strong></a>
          <span aria-hidden="true">→</span>
          <a href="#recommendations"><span>2</span><strong>Check nearby competition</strong></a>
          <span aria-hidden="true">→</span>
          <a href="#travel-time-check"><span>3</span><strong>Test different travel limits</strong></a>
          <span aria-hidden="true">→</span>
          <a href="#shortlist"><span>4</span><strong>See where to investigate</strong></a>
        </nav>

        <section className="content-section explore-section" id="explore">
          <div className="section-heading">
            <div>
              <p className="section-number">01–02 / Residents and travel</p>
              <h2>How many school-age residents are nearby or within reach?</h2>
            </div>
            <div className="section-summary">
              <span className="complete-badge">Complete</span>
              <p>I use residents aged 7–16 as a potential-market estimate because this broadly matches the P1–S4 scope. It does not measure willingness to enrol or ability to pay.</p>
            </div>
          </div>

          <div className="journey-guide" aria-label="What the estimated journey measures">
            <div><span>Start</span><strong>Residential-area centre</strong><p>A stand-in for where residents live, not an exact home or school.</p></div>
            <div className="journey-connector"><span aria-hidden="true">→</span><strong>Bus, MRT or both</strong><p>OneMap estimates the trip.</p></div>
            <div><span>End</span><strong>An exit of the candidate MRT station</strong><p>Not the door of a tuition centre.</p></div>
          </div>

          <div className="metric-guide" aria-label="Plain-language metric guide">
            <article>
              <span>Main view</span>
              <h3>Who can reach the area?</h3>
              <p>This counts estimated residents aged 7–16 in areas with a public-transport trip of up to 20 minutes to the MRT station. Separate walking and distance rules apply when a public-transport route is unavailable.</p>
            </article>
            <article>
              <span>Comparison view</span>
              <h3>Who lives near the station?</h3>
              <p>This estimates the target-age population living within 800 metres of the MRT exits. It is a nearby-population estimate, not a travel time.</p>
            </article>
            <article>
              <span>How to use both</span>
              <h3>Nearby does not always mean easy to reach</h3>
              <p>Switch between the two views, then click an MRT area to compare its values and ranking.</p>
            </article>
          </div>

          <details className="method-details">
            <summary>Show the modelling assumptions behind these measures</summary>
            <div>
              <p><strong>Where the journey starts and ends:</strong> OneMap estimated travel from the centre point of each residential area to an MRT exit. It is not a trip from a school or to an actual tuition unit. The weekday check uses Wednesday at 4 pm.</p>
              <p><strong>What “20 minutes” means:</strong> It is the maximum estimated public-transport time counted in the main view. If OneMap could not return a public-transport route, the model tried walking within 10 minutes. If that also failed, it used a straight-line distance of 800 metres. The distance fallback is not a travel-time estimate.</p>
              <p><strong>800-metre view:</strong> The population is estimated according to how much of each residential area overlaps the 800-metre boundary around station exits. This assumes residents are evenly distributed inside each area.</p>
              <p><strong>Why test 15 and 25 minutes too?</strong> No survey tells us how long families would travel for tuition. The 20-minute limit was a judgement made before seeing the results. The 15- and 25-minute checks show what changes when that judgement changes. Walking and distance fallbacks stay the same.</p>
            </div>
          </details>

          <div className="dashboard-frame">
            <div className="dashboard-toolbar">
              <label className="search-control">
                <span>⌕</span>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search MRT area"
                  aria-label="Search MRT area"
                />
              </label>
              <label className="select-control">
                <span>Region</span>
                <select value={region} onChange={(event) => setRegion(event.target.value)}>
                  {regions.map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
              <div className="metric-toggle" aria-label="Selected metric">
                <button className={metric === "accessibility" ? "active" : ""} onClick={() => setMetric("accessibility")}>Residents within travel reach</button>
                <button className={metric === "proximity" ? "active" : ""} onClick={() => setMetric("proximity")}>Residents living nearby</button>
              </div>
            </div>

            {loadingError ? <p className="error-message">{loadingError}</p> : null}
            <div className="dashboard-grid">
              <div className="map-panel">
                <div className="panel-heading">
                  <div><p>Geographic overview</p><span>{metric === "accessibility" ? "Dot size reflects the estimated target-age population in reachable residential areas" : "Dot size reflects the estimated target-age population within 800 m"}</span></div>
                  <div className="map-scope-toggle" aria-label="Map display">
                    <button className={mapScope === "leaders" ? "active" : ""} onClick={() => setMapScope("leaders")}>Top 10</button>
                    <button className={mapScope === "all" ? "active" : ""} onClick={() => setMapScope("all")}>All 146</button>
                  </div>
                </div>
                <div className="map-visual-wrap">
                  <div ref={mapContainerRef} className="interactive-map" role="application" aria-label="Interactive clustered map of Singapore MRT-area candidates" />
                  <div className="map-interaction-hint">Number = grouped MRT areas · dot = one area · click a cluster to split</div>
                </div>
                <div className="region-legend" aria-label="Singapore planning region colours">
                  <span className="legend-title">Planning region</span>
                  {REGION_STYLES.map((regionStyle) => (
                    <span className="legend-item" key={regionStyle.value}>
                      <i style={{ background: regionStyle.color }} />{regionStyle.label}
                    </span>
                  ))}
                </div>
                <div className="map-note"><span>Population estimates use official 2019 planning boundaries and ages 7–16</span><span>{mapScope === "leaders" ? "Top 10 for this one measure · not final recommendations" : "Clusters separate into individual MRT areas as you zoom"}</span></div>
              </div>

              <aside className="ranking-panel">
                <div className="panel-heading">
                  <div><p>{metric === "accessibility" ? "Most residents reached in the 20-minute public-transport test" : "Largest 800 m nearby-population estimates"}</p><span>{filteredStations.length} areas shown · estimated ages 7–16 population</span></div>
                  <span className="sort-label">Population only, highest first ↓</span>
                </div>
                <div className="ranking-list">
                  {filteredStations.slice(0, 12).map((station) => (
                    <button
                      className={`ranking-row ${station.id === selected?.id ? "selected" : ""}`}
                      key={station.id}
                      onClick={() => setSelectedId(station.id)}
                    >
                      <span className="rank">{String(stationRank(station)).padStart(2, "0")}</span>
                      <span className="station-copy"><strong><i className="region-dot" style={{ background: regionColor(station.region) }} />{station.name}</strong><small>{station.planningArea}</small></span>
                      <span className="bar-track"><i style={{ width: `${(stationValue(station) / maxPopulation) * 100}%`, background: regionColor(station.region) }} /></span>
                      <span className="station-value">{number.format(stationValue(station))}</span>
                    </button>
                  ))}
                </div>
              </aside>
            </div>

            {selected ? (
              <div className="selection-drawer">
                <div className="selected-title">
                  <span className="rank-pill" style={{ background: regionColor(selected.region) }}>#{stationRank(selected)}</span>
                  <div><strong>{selected.name}</strong><span>{selected.planningArea} · {metric === "accessibility" ? rankMovementLabel(selected) : selected.region}</span></div>
                </div>
                {metric === "accessibility" ? (
                  <>
                    <div className="selected-stat"><span>Estimated target-age population in reachable residential areas</span><strong>{number.format(selected.accessibilityPopulation)}</strong></div>
                    <div className="selected-stat"><span>Counted using public transport</span><strong>{number.format(selected.ptAccessiblePopulation)}</strong></div>
                    <div className="selected-stat"><span>Added using the walking estimate</span><strong>{number.format(selected.walkingAccessiblePopulation)}</strong></div>
                    <div className="selected-stat"><span>Added using the 800 m distance estimate</span><strong>{number.format(selected.proximityFallbackPopulation)}</strong></div>
                  </>
                ) : (
                  <>
                    <div className="selected-stat"><span>Estimated target-age population within 800 m</span><strong>{number.format(selected.population800m)}</strong></div>
                    <div className="selected-stat"><span>Estimated target-age population within a wider 1.2 km boundary</span><strong>{number.format(selected.population1200m)}</strong></div>
                    <div className="selected-stat"><span>Bus stops within 800 m</span><strong>{selected.busStops800m}</strong></div>
                    <div className="selected-stat"><span>Schools within 800 m</span><strong>{selected.schools800m}</strong></div>
                  </>
                )}
                <p className="map-stage-note"><strong>How to use this map:</strong> This view compares nearby population and travel access only. It does not identify the best place to open. <a href="#travel-time-check">See what changes at 15, 20 and 25 minutes.</a></p>
              </div>
            ) : null}
          </div>
        </section>

        <section className="content-section insight-section">
          <div className="insight-copy">
            <p className="section-number">Why both views are shown</p>
            <h2>Distance alone does not show how easily an area can be reached.</h2>
            <p>
              I compared the travel-route ranking with a simpler distance-based ranking.
              {h2 ? ` ${h2.movedTenRanks} of ${h2.validNodeCount}` : " Many"} MRT areas with usable results for both methods moved by at
              least 10 positions. This means that using distance alone could substantially change which areas appear attractive.
            </p>
            <div className="caution-card">
              <span>What this means</span>
              <p>Travel connections add useful information, but neither measure shows whether families will enrol or whether a centre will succeed.</p>
            </div>
            <details className="method-details compact-details">
              <summary>Show the technical comparison</summary>
              <div>
                <p>The formal test compares the 20-minute public-transport limit, with its fixed fallbacks, against a simpler rule that counts a residential area when its centre is within 800 metres of a station exit.</p>
                <p>These rules answer different questions and cover different geographic ranges. I therefore judged the practical effect by checking how much the ordering of MRT areas changed, rather than presenting a percentage difference between the two population estimates.</p>
              </div>
            </details>
          </div>
          <div className="insight-card">
            <div className="insight-card-head"><span>How much did the ordering change?</span><b>{h2?.materialDifference ? "Clearly different" : "Under review"}</b></div>
            <strong className="big-number">{h2?.movedTenRanks ?? 92}</strong>
            <span className="big-number-label">of {h2?.validNodeCount ?? 127} MRT areas with usable results for both methods moved by at least 10 positions when routes replaced straight-line distance.</span>
            <p className="insight-explanation">The way we measure access can change which areas appear attractive.</p>
            <div className="insight-footer"><strong>Overall ordering</strong><span>Moderately similar, not identical</span></div>
            <details className="dark-method-details">
              <summary>See the statistical measure</summary>
              <p>Spearman rank correlation was {h2?.rankCorrelation.toFixed(3) ?? "0.614"}. A value of 1 would mean that both methods placed every area in exactly the same order.</p>
            </details>
          </div>
        </section>

        <section className="content-section recommendation-section" id="recommendations">
          <div className="section-heading">
            <div>
              <p className="section-number">03–05 / Existing centres and the final choice</p>
              <h2>Two areas made the shortlist, but the evidence is not equally strong</h2>
            </div>
            <div className="section-summary">
              <span className="complete-badge">Areas, not units</span>
              <p>The shortlist combines estimated population, travel access and nearby tuition branches. It also checks what happens when the assumptions change.</p>
            </div>
          </div>

          <div className="decision-flow" aria-label="How the final decision was built">
            <article><span>1</span><div><strong>Compare potential reach</strong><p>Screen the MRT areas using target-age population and travel access.</p></div></article>
            <article><span>2</span><div><strong>Check existing centres</strong><p>Count physical tuition branches confirmed by their operators. Do not assume a place has no competitors just because the search found none.</p></div></article>
            <article><span>3</span><div><strong>See what changes</strong><p>Change the travel limit and other model choices. Flag areas that rank well only under certain choices.</p></div></article>
          </div>

          <details className="method-details">
            <summary>How were the areas ranked and shortlisted?</summary>
            <div>
              <p><strong>Compare like with like:</strong> Each area is compared on school-age population, travel access and verified nearby competition. Higher population and easier access receive stronger scores; fewer verified competitors receive a stronger competition score. A separate cautious version prevents “zero found” from automatically looking best.</p>
              <p><strong>Allow different priorities:</strong> There is no single objectively best weighting. The model repeats the comparison with five sets of operator priorities and different travel and competition assumptions. Before combining scores, it sets aside an area if another option is at least as strong on every measured dimension and stronger on at least one.</p>
              <p><strong>Choose results that hold up:</strong> The shortlist favours areas that appear in the top three more often, and an area must appear at least once with both the observed competitor counts and the cautious treatment. Shared financial assumptions do not distinguish areas. These rules identify places to investigate, not proven business opportunities.</p>
            </div>
          </details>

          <div className="uncertainty-callout" id="competition-uncertainty">
            <div className="uncertainty-heading">
              <span>How incomplete competitor data was handled</span>
              <h3>Follow how a search result becomes a cautious decision input</h3>
            </div>
            <div className="uncertainty-flow">
              <article>
                <span className="flow-number">1</span>
                <div><strong>Count physical branches</strong><p>Each verified branch is counted separately because it competes in its own surrounding area.</p></div>
              </article>
              <span className="flow-arrow" aria-hidden="true">→</span>
              <article>
                <span className="flow-number">2</span>
                <div><strong>Interpret “zero found” carefully</strong><p>It means this search verified no branch. The search is not an official registry, so it cannot prove that none exists.</p></div>
              </article>
              <span className="flow-arrow" aria-hidden="true">→</span>
              <article>
                <span className="flow-number">3</span>
                <div><strong>Test a more cautious ranking</strong><p>The model removes the automatic advantage of a zero-found result and checks whether the area still ranks well. This is a safeguard, not an invented branch count.</p></div>
              </article>
            </div>
          </div>

          <details className="method-details research-details">
            <summary>Extra research: does population access relate to existing branch locations?</summary>
            <div>
          <div className="subsection-heading">
            <span>Competition pattern</span>
            <h3>Do areas accessible to more students tend to have more tuition branches?</h3>
            <p>This check helps assess whether the accessible-population estimate reflects where operators have historically chosen to locate. It does not identify demand or prove that a new branch would succeed.</p>
          </div>

          <div className="evidence-strip">
            <div><strong>36</strong><span>candidate areas chosen before competitor results were viewed</span></div>
            <div><strong>40</strong><span>additional areas checked for a wider comparison</span></div>
            <div><strong>Positive, but modest</strong><span>relationship between accessible population and branch count</span></div>
            <p><strong>What I found:</strong> Areas accessible to more target-age residents tended to contain slightly more verified branches. The correlation was r = {finalAnalysis?.competition.h1.primary_design_weighted_result.weighted_correlation.toFixed(3) ?? "0.318"}, where values closer to 1 indicate a stronger positive relationship. This pattern is not strong enough to predict success and does not prove cause and effect. Rent, income, reputation, school mix and other unmeasured factors may also affect branch location.</p>
          </div>

            </div>
          </details>

          <div className="travel-time-check" id="travel-time-check">
            <div className="travel-time-heading">
              <div>
                <span>Check the travel-time assumption</span>
                <h3>What changes if the public-transport limit is 15, 20 or 25 minutes?</h3>
                <p>These are estimated trips from residential areas to MRT exits by bus, MRT or both. The limits are assumptions to test, not surveyed family preferences. The separate rules used when a route is unavailable stay unchanged.</p>
              </div>
              <a href="#shortlist">See what this means for the shortlist <ArrowIcon /></a>
            </div>
            <p className="travel-time-explainer">I compared the same original 36 MRT areas repeatedly, changing the journey timing, competitor-data assumptions and operator priorities. “In the top three every time” means the area stayed among the three highest-ranked options in every comparison. It does not mean it always ranked first.</p>
            {travelSensitivity ? (
              <div className="travel-time-grid" aria-label="How each shortlisted area performs when travel time changes">
                {(["SENGKANG", "SERANGOON"] as const).map((area) => (
                  <article className="travel-time-card" key={area}>
                    <div className="travel-time-card-head">
                      <h4>{area === "SENGKANG" ? "Sengkang" : "Serangoon"}</h4>
                      <span>{area === "SENGKANG" ? "Consistent result" : "Depends on travel time"}</span>
                    </div>
                    <p>{area === "SENGKANG" ? "Stays among the strongest options at all three travel limits." : "Ranks near the top only when a longer trip is allowed."}</p>
                    <dl className="travel-time-results">
                      {travelSensitivity.thresholds.map((caseResult) => (
                        <div key={caseResult.public_transport_minutes}>
                          <dt>{caseResult.public_transport_minutes} minutes</dt>
                          <dd className={caseResult.top_three_counts[area] === 0 ? "outside-top-three" : "in-top-three"}>
                            {travelResultLabel(caseResult.top_three_counts[area], travelSensitivity.comparisons_per_limit)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </article>
                ))}
              </div>
            ) : <p className="travel-time-loading">Loading the travel-time comparison…</p>}
            <div className="travel-time-takeaway">
              <strong>What this tells us</strong>
              <p>Sengkang stays strong at every tested limit. Serangoon only ranks near the top when 25 minutes are allowed. The original shortlist still names both areas, but Serangoon depends on a travel-time choice that has not been checked against how families actually travel for tuition.</p>
            </div>
            {travelSensitivity ? (
              <details className="method-details travel-time-details">
                <summary>See the exact comparison counts and how they were calculated</summary>
                <div>
                  <p>At each travel limit, the model compared a weekday and a Saturday, four ways of handling incomplete competitor information and five sets of operator priorities. This gives 40 comparisons. A count of zero means the area was never selected in the top three, not that it had no residents or could not be reached.</p>
                  <div className="travel-counts-wrap">
                    <table className="travel-counts">
                      <caption>Comparisons that selected the area in the top three</caption>
                      <thead><tr><th scope="col">Public-transport limit</th><th scope="col">Sengkang</th><th scope="col">Serangoon</th></tr></thead>
                      <tbody>{travelSensitivity.thresholds.map((caseResult) => (
                        <tr key={caseResult.public_transport_minutes}>
                          <th scope="row">{caseResult.public_transport_minutes} minutes</th>
                          <td>{caseResult.top_three_counts.SENGKANG} of {travelSensitivity.comparisons_per_limit}</td>
                          <td>{caseResult.top_three_counts.SERANGOON} of {travelSensitivity.comparisons_per_limit}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                  <p>These are different model settings, and some produce the same ranking. The counts show how an area's result changes across settings, not its chance of business success.</p>
                </div>
              </details>
            ) : null}
            <details className="method-details travel-time-details">
              <summary>Did changing the limit also change which areas were investigated?</summary>
              <div>
                <p>Yes, slightly. Of the original 36 areas, 34 are still selected with a 15-minute limit and 35 with a 25-minute limit. Macpherson enters both alternative lists, but comparable competitor information is not yet available for it. That is why the results above keep the original 36 areas fixed. They do not claim to rank the changed lists fully.</p>
                <p>These limits are tests of an assumption, not measured travel preferences. The comparison also uses only a weekday afternoon and a Saturday morning, not every possible class time.</p>
              </div>
            </details>
          </div>

          <div className="subsection-heading shortlist-heading" id="shortlist">
            <span>Final area shortlist</span>
            <h3>Which area is supported most consistently?</h3>
            <p>The earlier comparison changed travel limits, how uncertain competitor results were treated and what an operator valued most. Placing in the top three more often means the result changed less across these model checks. It does not tell us the probability that a centre would succeed.</p>
          </div>

          <div className="recommendation-grid">
            {(finalAnalysis?.decision.recommendations ?? []).map((item) => (
              <article className="recommendation-card" key={item.commercial_node_id}>
                <div className="recommendation-rank"><span>0{item.recommendation_rank}</span><i style={{ background: regionColor(item.planning_region) }} /></div>
                <h3>{item.display_name}</h3>
                <p className="recommendation-region">{item.planning_region.replace(" REGION", "")}</p>
                <div className="recommendation-stats">
                  <div><strong>{number.format(item.primary_accessible_population_proxy)}</strong><span>estimated residents aged 7–16 reached in the 20-minute public-transport test, including fallbacks</span></div>
                  <div><strong>{item.confirmed_competitors_10_min}</strong><span>verified P1–S4 maths tuition {item.confirmed_competitors_10_min === 1 ? "branch" : "branches"} within a 10-minute walk</span></div>
                  <div><strong>{item.selection_count === 200 ? "Consistent" : "Depends on assumptions"}</strong><span>{item.selection_count === 200 ? "in the top three in every original comparison" : "reaches the top three in only some original comparisons"}</span></div>
                </div>
                <details className="method-details compact-details"><summary>See the original comparison count</summary><div><p>Appeared in the top three in {item.selection_count} of {finalAnalysis?.decision.method.profile_ranking_evaluations ?? 200} original comparisons. This is a count of model settings, not a rank or a chance of success. The 15/20/25-minute check above uses 40 comparisons at each travel limit.</p></div></details>
                <p className="recommendation-copy">{recommendationInterpretation(item, travelSensitivity)}</p>
                <p className="due-diligence"><strong>Before signing a lease</strong>Check an actual unit, its total monthly cost, whether a tuition centre may operate there, fire-safety requirements, class capacity and interest from nearby parents.</p>
              </article>
            ))}
          </div>

          <div className="cost-boundary-callout" id="cost-boundary">
            <span>Why cost was not used to rank locations</span>
            <div>
              <h3>Comparable area-specific cost data was unavailable.</h3>
              <p>Applying the same assumed rent, fees and operating costs to every area cannot change which MRT area ranks higher. I therefore excluded those assumptions from the location ranking. The next stage should compare current total monthly costs after identifying actual units in the shortlisted areas.</p>
            </div>
          </div>

          <div className="conclusion-callout">
            <span>My conclusion</span>
            <h3>Investigate Sengkang first. Treat Serangoon as a travel-time-sensitive option.</h3>
            <p>Sengkang remained highly ranked at 15, 20 and 25 minutes. Serangoon ranked near the top only at 25 minutes, so I would not present it as equally well supported. Before choosing either area for a real centre, I would check available units, current rent and other costs, footfall, permission to use the space for tuition, safety rules and interest from nearby parents.</p>
          </div>

          <p className="decision-boundary">These are areas worth investigating, not specific units to lease. “Zero competitors found” means none were verified by this search, not that none exist. Availability, rent, required approvals and business success have not been established.</p>
        </section>

        <section className="content-section method-section" id="method">
          <div className="section-heading compact">
            <div><p className="section-number">Method</p><h2>From the whole country to a defensible shortlist</h2></div>
            <p className="method-intro">Each stage adds evidence. No single attractive metric is allowed to decide the answer alone.</p>
          </div>
          <div className="method-grid">
            {[
              ["01", "Who lives nearby?", "Complete", "done", "Estimate the ages 7–16 population within 800 m, then see what changes when the nearby area widens to 1.2 km."],
              ["02", "Who can reach it?", "Complete", "done", "Estimate public-transport journeys from 332 residential-area centre points to 146 MRT areas. Use the stated walking and distance rules if a route is unavailable."],
              ["03", "Who already operates nearby?", "Complete", "done", "Search for tuition branches, check details on the operators’ own pages and measure walking routes to MRT areas."],
              ["04", "Can costs distinguish the areas?", "Not used in ranking", "done", "No. Reliable area-specific rent data was unavailable, and identical cost assumptions cannot change the location order."],
              ["05", "Does the result stay stable?", "Complete", "done", "Compare results when travel limits, competitor uncertainty and operator priorities change. Flag results that rely on one assumption."],
            ].map(([step, title, status, state, description]) => (
              <article className={`method-card ${state}`} key={step}>
                <div className="method-card-top"><span>{step}</span><StageIcon state={state as "done" | "active" | "pending"} /></div>
                <h3>{title}</h3>
                <p>{description}</p>
                <strong>{status}</strong>
              </article>
            ))}
          </div>
        </section>

        <section className="content-section data-guide-section" id="data-guide">
          <div className="section-heading compact">
            <div><p className="section-number">How to use this analysis</p><h2>Useful for screening areas, not for signing a lease.</h2></div>
            <p className="method-intro">Every headline figure is reproducible, but each answers a limited question. Use the shortlist to decide where deeper commercial research should begin.</p>
          </div>
          <div className="data-guide-grid">
            <article><span>Population estimate</span><h3>Estimated residents, not customers</h3><p>I use ages 7–16 because they broadly correspond to the P1–S4 education years in scope. The official residential-area population data cannot show who takes tuition, who would enrol or which households can afford it.</p></article>
            <article><span>Recommendation</span><h3>An MRT area, not a unit to lease</h3><p>The result identifies areas worth investigating under stated assumptions. It does not show that a suitable unit is available, affordable or approved for tuition use.</p></article>
            <article><span>For researchers</span><h3>Inspect the released evidence</h3><p>Download the public results and the later travel-time check to inspect the numbers yourself.</p><div className="download-links"><a href="/data/node_accessibility_metrics.csv" download>Travel-access CSV</a><a href="/data/node_proximity_metrics.csv" download>Nearby-population CSV</a><a href="/data/final-analysis.json" download>Original analysis JSON</a><a href="/data/travel-time-sensitivity.json" download>15/20/25-minute check JSON</a></div></article>
          </div>
        </section>

        <section className="content-section roadmap-section" id="roadmap">
          <div className="roadmap-card">
            <div>
              <p className="section-number">What happens next</p>
              <h2>Test the shortlist against real premises and local market evidence.</h2>
              <p>The analysis narrows where an operator could investigate; it does not decide which unit to lease. I would start with actual units in Sengkang. I would also check whether Serangoon could draw families from as far away as the 25-minute test assumes. For any unit, I would check its total monthly cost, footfall, permission to operate, fire safety, room capacity, achievable fees and feedback from nearby parents.</p>
            </div>
            <div className="progress-preview">
              <div className="progress-label"><span>What this project delivers</span><strong>Area comparison complete</strong></div>
              <span>Next real-world step: investigate actual units and speak to nearby parents. This is separate from the completed area analysis.</span>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="brand"><span className="brand-mark"><i /><i /><i /></span><span>Tuition Location Intelligence</span></div>
        <p>Portfolio case study · Results are analytical estimates, not guarantees of business success.</p>
        <a href="#top">Back to top ↑</a>
      </footer>
    </div>
  );
}
