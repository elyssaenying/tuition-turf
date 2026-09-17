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
  longitude: number;
  latitude: number;
};

type GeoFeature = {
  geometry: { coordinates: [number, number] };
  properties: { commercial_node_id: string };
};

type BoundaryFeature = {
  geometry: {
    type: "Polygon" | "MultiPolygon";
    coordinates: number[][][] | number[][][][];
  };
};

const number = new Intl.NumberFormat("en-SG", { maximumFractionDigits: 0 });

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
  const [loadingError, setLoadingError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("/data/node_proximity_metrics.csv").then((response) => response.text()),
      fetch("/data/node_inspection.geojson").then((response) => response.json()),
      fetch("/data/mp2019_subzones.geojson").then((response) => response.json()),
    ])
      .then(([csv, geojson, subzoneGeojson]) => {
        const rows = parseCsv(csv);
        const headers = rows[0];
        const column = (name: string) => headers.indexOf(name);
        const coordinates = new Map<string, [number, number]>(
          (geojson.features as GeoFeature[]).map((feature) => [
            feature.properties.commercial_node_id,
            feature.geometry.coordinates,
          ]),
        );
        const loaded = rows.slice(1).map((row) => {
          const id = row[column("commercial_node_id")];
          const point = coordinates.get(id) ?? [103.82, 1.35];
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
            longitude: point[0],
            latitude: point[1],
          };
        });
        loaded.sort((a, b) => a.rank - b.rank);
        setStations(loaded);
        setBoundaries(subzoneGeojson.features as BoundaryFeature[]);
        setSelectedId(loaded[0]?.id ?? "");
      })
      .catch(() => setLoadingError("The local dashboard data could not be loaded."));
  }, []);

  const regions = useMemo(
    () => ["All regions", ...Array.from(new Set(stations.map((station) => station.region))).sort()],
    [stations],
  );

  const filteredStations = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return stations.filter(
      (station) =>
        (region === "All regions" || station.region === region) &&
        (!normalizedQuery ||
          station.name.toLowerCase().includes(normalizedQuery) ||
          station.planningArea.toLowerCase().includes(normalizedQuery)),
    );
  }, [stations, region, query]);

  const selected = stations.find((station) => station.id === selectedId) ?? stations[0];
  const maxPopulation = Math.max(...stations.map((station) => station.population800m), 1);
  const mappedStations = useMemo(() => {
    if (mapScope === "all") return filteredStations;
    return filteredStations.filter((station) => station.rank <= 10 || station.id === selected?.id);
  }, [filteredStations, mapScope, selected?.id]);

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
          rank: station.rank,
          population: Math.round(station.population800m),
        },
      })),
    }),
    [mappedStations],
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
      if (!map.getSource("stations")) return;

      const visibleClusterIds = new Set<number>();
      for (const feature of map.querySourceFeatures("stations")) {
        const clusterId = Number(feature.properties?.cluster_id);
        const count = Number(feature.properties?.point_count);
        if (!feature.properties?.cluster || !Number.isFinite(clusterId) || feature.geometry.type !== "Point") continue;

        visibleClusterIds.add(clusterId);
        if (clusterCountMarkers.has(clusterId)) continue;

        const markerElement = document.createElement("div");
        markerElement.className = "map-cluster-count";
        markerElement.textContent = String(feature.properties?.point_count_abbreviated ?? count);
        markerElement.setAttribute("aria-hidden", "true");
        markerElement.style.setProperty("--cluster-size", `${count >= 24 ? 42 : count >= 10 ? 34 : count >= 4 ? 26 : 20}px`);

        const marker = new maplibregl.Marker({ element: markerElement, anchor: "center" })
          .setLngLat(feature.geometry.coordinates as [number, number])
          .addTo(map);
        clusterCountMarkers.set(clusterId, marker);
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
        paint: { "fill-color": "#dce6e0", "fill-opacity": 0.96 },
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
            "#f06c4f",
            ["interpolate", ["linear"], ["get", "population"], 0, "#a7bdb6", 10084, "#0d695f"],
          ],
          "circle-radius": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            7,
            ["interpolate", ["linear"], ["get", "population"], 0, 3.2, 10084, 5.8],
          ],
          "circle-stroke-color": "#fffdf7",
          "circle-stroke-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.5, 1.2],
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
          <a href="#method">Method</a>
          <a href="#roadmap">Roadmap</a>
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
              <a className="primary-button" href="#explore">Explore the first analysis <ArrowIcon /></a>
              <a className="text-link" href="#method">See how it works</a>
            </div>
          </div>
          <div className="hero-metrics" aria-label="Project summary">
            <div><strong>146</strong><span>MRT areas screened</span></div>
            <div><strong>332</strong><span>Residential subzones</span></div>
            <div><strong>5</strong><span>Decision stages</span></div>
            <div className="status-metric"><strong>01</strong><span><b /> stage complete</span></div>
          </div>
        </section>

        <section className="status-strip" aria-label="Dashboard status">
          <span className="live-dot" />
          <strong>First-cut preview</strong>
          <span>Real proximity data · unfinished stages clearly marked</span>
          <span className="status-date">Data snapshot: 17 Sep 2026</span>
        </section>

        <section className="content-section explore-section" id="explore">
          <div className="section-heading">
            <div>
              <p className="section-number">01 / Population proximity</p>
              <h2>Explore all 146 MRT areas</h2>
            </div>
            <div className="section-summary">
              <span className="complete-badge">Complete</span>
              <p>Estimated residents aged 7–16 inside an 800 m exit-union catchment.</p>
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
                <button className="active">800 m baseline</button>
                <button disabled>Accessibility soon</button>
              </div>
            </div>

            {loadingError ? <p className="error-message">{loadingError}</p> : null}
            <div className="dashboard-grid">
              <div className="map-panel">
                <div className="panel-heading">
                  <div><p>Geographic overview</p><span>MRT-area anchor points</span></div>
                  <div className="map-scope-toggle" aria-label="Map display">
                    <button className={mapScope === "leaders" ? "active" : ""} onClick={() => setMapScope("leaders")}>Top 10</button>
                    <button className={mapScope === "all" ? "active" : ""} onClick={() => setMapScope("all")}>All 146</button>
                  </div>
                </div>
                <div className="map-visual-wrap">
                  <div ref={mapContainerRef} className="interactive-map" role="application" aria-label="Interactive clustered map of Singapore MRT-area candidates" />
                  <div className="map-interaction-hint">Number = grouped MRT areas · dot = one area · click a cluster to split</div>
                </div>
                <div className="map-note"><span>Real MP2019 subzone boundaries and station-complex anchors</span><span>{mapScope === "leaders" ? "Top 10 population signals · not a shortlist" : "Clusters separate into individual MRT areas as you zoom"}</span></div>
              </div>

              <aside className="ranking-panel">
                <div className="panel-heading">
                  <div><p>Population-proximity ranking</p><span>{filteredStations.length} areas shown</span></div>
                  <span className="sort-label">Highest first ↓</span>
                </div>
                <div className="ranking-list">
                  {filteredStations.slice(0, 12).map((station) => (
                    <button
                      className={`ranking-row ${station.id === selected?.id ? "selected" : ""}`}
                      key={station.id}
                      onClick={() => setSelectedId(station.id)}
                    >
                      <span className="rank">{String(station.rank).padStart(2, "0")}</span>
                      <span className="station-copy"><strong>{station.name}</strong><small>{station.planningArea}</small></span>
                      <span className="bar-track"><i style={{ width: `${(station.population800m / maxPopulation) * 100}%` }} /></span>
                      <span className="station-value">{number.format(station.population800m)}</span>
                    </button>
                  ))}
                </div>
              </aside>
            </div>

            {selected ? (
              <div className="selection-drawer">
                <div className="selected-title">
                  <span className="rank-pill">#{selected.rank}</span>
                  <div><strong>{selected.name}</strong><span>{selected.planningArea} · {selected.region}</span></div>
                </div>
                <div className="selected-stat"><span>800 m population proxy</span><strong>{number.format(selected.population800m)}</strong></div>
                <div className="selected-stat"><span>1,200 m sensitivity</span><strong>{number.format(selected.population1200m)}</strong></div>
                <div className="selected-stat"><span>Bus stops nearby</span><strong>{selected.busStops800m}</strong></div>
                <div className="selected-stat"><span>Schools nearby</span><strong>{selected.schools800m}</strong></div>
                <span className="not-recommendation">Early signal · not a recommendation</span>
              </div>
            ) : null}
          </div>
        </section>

        <section className="content-section insight-section">
          <div className="insight-copy">
            <p className="section-number">What the first stage says</p>
            <h2>Strong residential proximity appears outside the city core.</h2>
            <p>
              Sengkang currently leads the completed proximity baseline. That means more estimated
              residents aged 7–16 fall inside its 800 m straight-line catchment—not that it is already
              the best place to open.
            </p>
            <div className="caution-card">
              <span>Important</span>
              <p>Accessibility, competition and commercial viability can still change the eventual shortlist.</p>
            </div>
          </div>
          <div className="insight-card">
            <div className="insight-card-head"><span>Leading proximity signal</span><b>Completed analysis</b></div>
            <strong className="big-number">10,084</strong>
            <span className="big-number-label">estimated residents aged 7–16 within 800 m</span>
            <Sparkline values={stations.slice(0, 12).map((station) => station.population800m).reverse()} />
            <div className="insight-footer"><strong>Sengkang</strong><span>Rank 1 of 146</span></div>
          </div>
        </section>

        <section className="content-section method-section" id="method">
          <div className="section-heading compact">
            <div><p className="section-number">Method</p><h2>From the whole country to a defensible shortlist</h2></div>
            <p className="method-intro">Each stage adds evidence. No single attractive metric is allowed to decide the answer alone.</p>
          </div>
          <div className="method-grid">
            {[
              ["01", "Population proximity", "Complete", "done", "Area-weighted ages 7–16 population inside 800 m and 1,200 m station-exit catchments."],
              ["02", "Real accessibility", "Running", "active", "Public-transport journeys from 332 residential subzones to all 146 MRT areas."],
              ["03", "Competition", "Next", "pending", "Confirmed mathematics-tuition branches around viable candidate areas."],
              ["04", "Economics", "Planned", "pending", "Break-even enrolment, required capture share and occupancy-cost sensitivity."],
              ["05", "Recommendation", "Locked", "pending", "Up to three conditional locations, only after quality and robustness checks."],
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
              <p className="section-number">Next analytical release</p>
              <h2>Travel-time accessibility is being calculated.</h2>
              <p>The final dashboard will replace this preview with audited national results—never made-up placeholders.</p>
            </div>
            <div className="progress-preview">
              <div className="progress-label"><span>National route collection</span><strong>In progress</strong></div>
              <div className="skeleton-bars"><i /><i /><i /><i /></div>
              <span>96,944 planned public-transport routes · 500 m walking limit</span>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="brand"><span className="brand-mark"><i /><i /><i /></span><span>Tuition Location Intelligence</span></div>
        <p>Portfolio preview · Results are analytical estimates, not guarantees of business success.</p>
        <a href="#top">Back to top ↑</a>
      </footer>
    </div>
  );
}
