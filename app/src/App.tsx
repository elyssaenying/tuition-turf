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
  rationale: string;
  next_due_diligence: string;
};

type WatchlistItem = Recommendation & { watchlist_reason: string };

type FinalAnalysis = {
  competition: {
    coverage: {
      fixed_queries_completed: number;
      fixed_queries_planned: number;
      unique_mrt_areas: number;
      unique_confirmed_physical_branches: number;
      walking_routes_completed: number;
      all_competitor_walking_routes_completed: number;
    };
    h1: {
      direction_observed: boolean;
      inferential_status: string;
      primary_design_weighted_result: { weighted_correlation: number };
      interpretation: string;
    };
    strategic_benchmark: {
      interpretation: string;
      claim_boundary: string;
      nodes: Array<{
        display_name: string;
        confirmed_within_10_min_walk: number;
        possible_within_10_min_walk: number;
        confirmed_within_15_min_walk: number;
      }>;
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
      break_even_active_enrolments: number;
      break_even_utilisation: number;
    }>;
    recommendations: Recommendation[];
    competition_recheck_watchlist: WatchlistItem[];
    claim_boundary: string;
  };
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
  if (movement === 0) return "same rank as proximity";
  return `${movement > 0 ? "rose" : "fell"} ${Math.abs(movement)} rank${Math.abs(movement) === 1 ? "" : "s"} vs proximity`;
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M4 10h11M11 6l4 4-4 4" />
    </svg>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(...values);
  const points = values
    .map((value, index) => `${(index / (values.length - 1)) * 100},${34 - (value / max) * 28}`)
    .join(" ");
  return (
    <svg className="sparkline" viewBox="0 0 100 36" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={points} />
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
  const [loadingError, setLoadingError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("/data/node_proximity_metrics.csv").then((response) => response.text()),
      fetch("/data/node_accessibility_metrics.csv").then((response) => response.text()),
      fetch("/data/h2-results.json").then((response) => response.json()),
      fetch("/data/node_inspection.geojson").then((response) => response.json()),
      fetch("/data/mp2019_subzones.geojson").then((response) => response.json()),
      fetch("/data/final-analysis.json").then((response) => response.json()),
    ])
      .then(([csv, accessibilityCsv, h2Result, geojson, subzoneGeojson, completedAnalysis]) => {
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
        detail.textContent = `Rank ${feature?.properties?.rank} · ${number.format(Number(feature?.properties?.population ?? 0))}`;
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
              Starting with every current MRT area in Singapore, this project combines population,
              accessibility, competition and economics to build a transparent shortlist.
            </p>
            <div className="hero-actions">
              <a className="primary-button" href="#explore">Explore the audited analysis <ArrowIcon /></a>
              <a className="text-link" href="#method">See how it works</a>
            </div>
          </div>
          <div className="hero-metrics" aria-label="Project summary">
            <div><strong>146</strong><span>MRT areas screened</span></div>
            <div><strong>332</strong><span>Residential subzones</span></div>
            <div><strong>5</strong><span>Decision stages</span></div>
            <div className="status-metric"><strong>05</strong><span><b /> stages complete</span></div>
          </div>
        </section>

        <section className="status-strip" aria-label="Dashboard status">
          <span className="live-dot" />
          <strong>Analysis complete</strong>
          <span>146 MRT areas screened · {finalAnalysis?.competition.coverage.fixed_queries_completed ?? 156} competitor searches · quality checks passed</span>
          <span className="status-date">Analysis completed: 18 Sep 2026</span>
        </section>

        <section className="content-section explore-section" id="explore">
          <div className="section-heading">
            <div>
              <p className="section-number">01–02 / Demand and accessibility</p>
              <h2>See what changes when travel time replaces distance</h2>
            </div>
            <div className="section-summary">
              <span className="complete-badge">Complete</span>
              <p>Compare the 800 m proximity baseline with audited 20-minute public-transport accessibility.</p>
            </div>
          </div>

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
                <button className={metric === "accessibility" ? "active" : ""} onClick={() => setMetric("accessibility")}>20 min accessibility</button>
                <button className={metric === "proximity" ? "active" : ""} onClick={() => setMetric("proximity")}>800 m proximity</button>
              </div>
            </div>

            {loadingError ? <p className="error-message">{loadingError}</p> : null}
            <div className="dashboard-grid">
              <div className="map-panel">
                <div className="panel-heading">
                  <div><p>Geographic overview</p><span>{metric === "accessibility" ? "Dot size reflects accessible population" : "Dot size reflects nearby population"}</span></div>
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
                <div className="map-note"><span>Real MP2019 subzones and station-complex anchors</span><span>{mapScope === "leaders" ? `Top 10 ${metric === "accessibility" ? "accessibility" : "proximity"} signals · not a shortlist` : "Clusters separate into individual MRT areas as you zoom"}</span></div>
              </div>

              <aside className="ranking-panel">
                <div className="panel-heading">
                  <div><p>{metric === "accessibility" ? "Travel-time accessibility ranking" : "Population-proximity ranking"}</p><span>{filteredStations.length} areas shown</span></div>
                  <span className="sort-label">Highest first ↓</span>
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
                    <div className="selected-stat"><span>Accessible population</span><strong>{number.format(selected.accessibilityPopulation)}</strong></div>
                    <div className="selected-stat"><span>Via public transport</span><strong>{number.format(selected.ptAccessiblePopulation)}</strong></div>
                    <div className="selected-stat"><span>Via walking fallback</span><strong>{number.format(selected.walkingAccessiblePopulation)}</strong></div>
                    <div className="selected-stat"><span>Via proximity fallback</span><strong>{number.format(selected.proximityFallbackPopulation)}</strong></div>
                  </>
                ) : (
                  <>
                    <div className="selected-stat"><span>800 m population proxy</span><strong>{number.format(selected.population800m)}</strong></div>
                    <div className="selected-stat"><span>1,200 m sensitivity</span><strong>{number.format(selected.population1200m)}</strong></div>
                    <div className="selected-stat"><span>Bus stops nearby</span><strong>{selected.busStops800m}</strong></div>
                    <div className="selected-stat"><span>Schools nearby</span><strong>{selected.schools800m}</strong></div>
                  </>
                )}
                <span className="not-recommendation">Early signal · not a recommendation</span>
              </div>
            ) : null}
          </div>
        </section>

        <section className="content-section insight-section">
          <div className="insight-copy">
            <p className="section-number">What changed</p>
            <h2>Travel time materially reshapes the national picture.</h2>
            <p>
              The median MRT area's accessibility estimate differs from its straight-line baseline by
              {h2 ? ` ${Math.round(h2.medianDifference * 100)}%` : " a material amount"}. Network connections
              reveal reach that a simple circle around a station cannot measure.
            </p>
            <div className="caution-card">
              <span>Important</span>
              <p>This is a stronger screen, not the final answer. Competition, commercial qualification and economics still matter.</p>
            </div>
          </div>
          <div className="insight-card">
            <div className="insight-card-head"><span>Rank movement diagnostic</span><b>{h2?.materialDifference ? "Material difference" : "Under review"}</b></div>
            <strong className="big-number">{h2?.movedTenRanks ?? 92}</strong>
            <span className="big-number-label">of {h2?.validNodeCount ?? 127} comparable MRT areas moved at least 10 ranks</span>
            <Sparkline values={stations.slice(0, 12).map((station) => station.accessibilityPopulation).reverse()} />
            <div className="insight-footer"><strong>Rank correlation</strong><span>{h2?.rankCorrelation.toFixed(3) ?? "0.614"}</span></div>
          </div>
        </section>

        <section className="content-section recommendation-section" id="recommendations">
          <div className="section-heading">
            <div>
              <p className="section-number">03–05 / Competition, economics and decision</p>
              <h2>{finalAnalysis?.decision.recommendations.length ?? 2} areas remain defensible after the competition stress test</h2>
            </div>
            <div className="section-summary">
              <span className="complete-badge">Conditional result</span>
              <p>{finalAnalysis?.decision.method.profile_ranking_evaluations ?? 200} predeclared profile evaluations across demand, accessibility and competition sensitivities.</p>
            </div>
          </div>

          <div className="recommendation-grid">
            {(finalAnalysis?.decision.recommendations ?? []).map((item) => (
              <article className="recommendation-card" key={item.commercial_node_id}>
                <div className="recommendation-rank"><span>0{item.recommendation_rank}</span><i style={{ background: regionColor(item.planning_region) }} /></div>
                <h3>{item.display_name}</h3>
                <p className="recommendation-region">{item.planning_region.replace(" REGION", "")}</p>
                <div className="recommendation-stats">
                  <div><strong>{number.format(item.primary_accessible_population_proxy)}</strong><span>reachable population proxy</span></div>
                  <div><strong>{item.confirmed_competitors_10_min}</strong><span>confirmed found ≤10 min</span></div>
                  <div><strong>{Math.round(item.top_three_frequency * 100)}%</strong><span>top-three frequency</span></div>
                </div>
                <p className="recommendation-copy">{item.rationale}</p>
                <p className="due-diligence"><strong>Before signing a lease</strong>{item.next_due_diligence}</p>
              </article>
            ))}
          </div>

          {finalAnalysis?.decision.competition_recheck_watchlist.length ? (
            <div className="benchmark-callout">
              <span>Competition-recheck watchlist</span>
              <strong>{finalAnalysis.decision.competition_recheck_watchlist.map((item) => item.display_name).join(" and ")} are not final recommendations.</strong>
              <p>They rank well only when zero confirmed discoveries receive the most favourable competition score. Recheck local competitor coverage before promoting either area.</p>
            </div>
          ) : null}

          <div className="evidence-strip">
            <div><strong>{finalAnalysis?.competition.coverage.unique_confirmed_physical_branches ?? "—"}</strong><span>unique verified branches</span></div>
            <div><strong>{number.format(finalAnalysis?.competition.coverage.all_competitor_walking_routes_completed ?? 0)}</strong><span>competitor walking routes</span></div>
            <div><strong>{finalAnalysis?.competition.h1.primary_design_weighted_result.weighted_correlation.toFixed(2) ?? "—"}</strong><span>H1 weighted correlation</span></div>
            <p>{finalAnalysis?.competition.h1.interpretation ?? "Loading final competition result…"} It remains descriptive/inconclusive. Discovery is fixed and reproducible from safe aggregates, but not a complete business registry.</p>
          </div>

          {finalAnalysis ? (() => {
            const beautyWorld = finalAnalysis.competition.strategic_benchmark.nodes.find((item) => item.display_name === "BEAUTY WORLD");
            return (
              <div className="benchmark-callout">
                <span>Bukit Timah benchmark</span>
                <strong>Beauty World has {beautyWorld?.confirmed_within_10_min_walk ?? 8} confirmed competitors inside 10 minutes.</strong>
                <p>{finalAnalysis.competition.strategic_benchmark.interpretation} {finalAnalysis.competition.strategic_benchmark.claim_boundary}</p>
              </div>
            );
          })() : null}

          <div className="finance-grid">
            <div className="finance-intro"><span>Illustrative economics</span><h3>Same assumptions for every area</h3><p>No unsupported local rent differences were invented. Finance is reported separately because common assumptions do not change the location order.</p></div>
            {(finalAnalysis?.decision.financial_scenarios ?? []).map((scenario) => (
              <article key={scenario.scenario_id}>
                <span>{scenario.scenario_id}</span>
                <strong>{scenario.break_even_active_enrolments} students</strong>
                <small>{Math.round(scenario.break_even_utilisation * 100)}% of illustrative capacity · SGD {number.format(scenario.occupancy_cost)}/month occupancy assumption</small>
              </article>
            ))}
          </div>

          <p className="decision-boundary">{finalAnalysis?.decision.claim_boundary}</p>
        </section>

        <section className="content-section method-section" id="method">
          <div className="section-heading compact">
            <div><p className="section-number">Method</p><h2>From the whole country to a defensible shortlist</h2></div>
            <p className="method-intro">Each stage adds evidence. No single attractive metric is allowed to decide the answer alone.</p>
          </div>
          <div className="method-grid">
            {[
              ["01", "Population proximity", "Complete", "done", "Area-weighted ages 7–16 population inside 800 m and 1,200 m station-exit catchments."],
              ["02", "Real accessibility", "Complete", "done", "96,944 public-transport journeys from 332 residential subzones to all 146 MRT areas."],
              ["03", "Competition", "Complete", "done", "156 fixed searches, operator-page validation and actual walking routes around 78 audited MRT areas."],
              ["04", "Economics", "Complete", "done", "Three transparent operator-assumption cases for break-even and occupancy-cost sensitivity."],
              ["05", "Recommendation", "Complete", "done", "Up to three conditional areas selected across the frozen Pareto and five-profile grid."],
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

        <section className="content-section roadmap-section" id="roadmap">
          <div className="roadmap-card">
            <div>
              <p className="section-number">What happens next</p>
              <h2>Validate a real unit before making a lease decision.</h2>
              <p>The analytical shortlist is complete. The next work is practical due diligence: current availability and all-in rent, intended-use approval, owner consent, fire safety, room capacity and local parent validation.</p>
            </div>
            <div className="progress-preview">
              <div className="progress-label"><span>Core portfolio analysis</span><strong>100% complete</strong></div>
              <div className="completion-bar"><i /></div>
              <span>All 5 stages complete · conditional area result · unit due diligence remains</span>
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
