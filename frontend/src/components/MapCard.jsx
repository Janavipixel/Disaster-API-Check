import React, { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export default function MapCard({ incident, recenterTrigger }) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const baseLayersRef = useRef({});
  const currentBaseLayerRef = useRef(null);
  const bboxLayerRef = useRef(null);
  const markerLayerRef = useRef(null);
  const firmsLayerRef = useRef(null);

  const [basemap, setBasemap] = useState('satellite');
  const [showBbox, setShowBbox] = useState(true);
  const [showMarkers, setShowMarkers] = useState(true);

  // Initialize Leaflet Map once
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    delete L.Icon.Default.prototype._getIconUrl;
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
      iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
      shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
    });

    const initialCoords = incident?.primary_coordinates
      ? [incident.primary_coordinates.latitude, incident.primary_coordinates.longitude]
      : [9.919, 76.403];

    const map = L.map(mapContainerRef.current, {
      zoomControl: true,
      attributionControl: true,
      preferCanvas: true,
    }).setView(initialCoords, 12);

    mapInstanceRef.current = map;

    // Basemaps
    const darkCanvas = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
      {
        attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
        maxZoom: 16,
      }
    );

    const satelliteLayer = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {
        attribution: 'Source: Esri, Maxar, Earthstar Geographics, USDA, USGS',
        maxZoom: 19,
      }
    );

    const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    });

    baseLayersRef.current = {
      dark: darkCanvas,
      satellite: satelliteLayer,
      osm: osm,
    };

    // Default to Satellite
    satelliteLayer.addTo(map);
    currentBaseLayerRef.current = satelliteLayer;

    // Layer Groups
    bboxLayerRef.current = L.layerGroup().addTo(map);
    markerLayerRef.current = L.layerGroup().addTo(map);
    firmsLayerRef.current = L.layerGroup().addTo(map);

    const timer = setTimeout(() => {
      map.invalidateSize();
    }, 250);

    return () => {
      clearTimeout(timer);
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Handle Basemap Switch
  const handleBasemapChange = (type) => {
    setBasemap(type);
    const map = mapInstanceRef.current;
    if (!map || !baseLayersRef.current[type]) return;

    if (currentBaseLayerRef.current) {
      map.removeLayer(currentBaseLayerRef.current);
    }
    const newLayer = baseLayersRef.current[type];
    newLayer.addTo(map);
    newLayer.bringToBack();
    currentBaseLayerRef.current = newLayer;
  };

  // Recenter / Fit Bounds on Rectangle
  const handleFitBbox = useCallback(() => {
    const map = mapInstanceRef.current;
    if (!map || !incident) return;

    if (incident.bbox && incident.bbox.length === 4) {
      const [minLon, minLat, maxLon, maxLat] = incident.bbox;
      map.fitBounds(
        [
          [minLat, minLon],
          [maxLat, maxLon],
        ],
        { padding: [25, 25], maxZoom: 13, animate: true }
      );
    } else if (incident.primary_coordinates) {
      map.setView(
        [incident.primary_coordinates.latitude, incident.primary_coordinates.longitude],
        12,
        { animate: true }
      );
    }
  }, [incident]);

  // Recenter when recenterTrigger changes
  useEffect(() => {
    if (recenterTrigger > 0) {
      handleFitBbox();
    }
  }, [recenterTrigger, handleFitBbox]);

  // Update Layers when Incident, showBbox, or showMarkers change
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !incident) return;

    bboxLayerRef.current?.clearLayers();
    markerLayerRef.current?.clearLayers();
    firmsLayerRef.current?.clearLayers();

    const { primary_coordinates, bbox, firms, location } = incident;

    // 1. AOI Bounding Box
    if (bbox && bbox.length === 4 && showBbox) {
      const [minLon, minLat, maxLon, maxLat] = bbox;
      const rect = L.rectangle(
        [
          [minLat, minLon],
          [maxLat, maxLon],
        ],
        {
          color: '#38bdf8',
          weight: 1.8,
          dashArray: '5, 5',
          fillColor: '#38bdf8',
          fillOpacity: 0.12,
        }
      ).bindTooltip(`<b>Area of Interest</b><br>${location}`, { sticky: true });

      bboxLayerRef.current.addLayer(rect);
    }

    // 2. Custom SVG Map Marker
    if (primary_coordinates && primary_coordinates.latitude != null && showMarkers) {
      const lat = primary_coordinates.latitude;
      const lon = primary_coordinates.longitude;

      const cleanPinIcon = L.divIcon({
        className: 'custom-leaflet-marker',
        html: `
          <div style="position:relative;width:26px;height:32px;">
            <svg viewBox="0 0 24 32" width="26" height="32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 0C5.37 0 0 5.37 0 12C0 21 12 32 12 32C12 32 24 21 24 12C24 5.37 18.63 0 12 0Z" fill="#2563eb"/>
              <circle cx="12" cy="12" r="5" fill="#ffffff"/>
            </svg>
          </div>
        `,
        iconSize: [26, 32],
        iconAnchor: [13, 32],
        popupAnchor: [0, -30],
      });

      const depthInfo = primary_coordinates.depth_km
        ? `<br><b>Focal Depth:</b> ${primary_coordinates.depth_km} km`
        : '';

      const marker = L.marker([lat, lon], { icon: cleanPinIcon }).bindPopup(`
        <div style="font-family:'Inter',sans-serif;font-size:12px;color:#f8fafc;line-height:1.45;padding:2px;">
          <b style="font-size:13px;color:#60a5fa;">${primary_coordinates.coordinate_label || 'Incident Center'}</b><br>
          <b>Location:</b> ${location}<br>
          <b>Coordinates:</b> ${lat.toFixed(4)}, ${lon.toFixed(4)}${depthInfo}<br>
          <span style="color:#94a3b8;font-size:11px;">Source: ${primary_coordinates.source}</span>
        </div>
      `);

      markerLayerRef.current.addLayer(marker);
    }

    // 3. NASA FIRMS Hotspots
    if (firms?.matched_detections?.length > 0) {
      firms.matched_detections.forEach((det, idx) => {
        const circle = L.circleMarker([det.latitude, det.longitude], {
          radius: 6,
          color: '#ef4444',
          fillColor: '#f97316',
          fillOpacity: 0.85,
          weight: 1.5,
        }).bindTooltip(
          `<b>Thermal Hotspot #${idx + 1}</b><br>FRP: ${det.frp || 'N/A'} MW | Conf: ${det.confidence}`,
          { sticky: true }
        );
        firmsLayerRef.current.addLayer(circle);
      });
    }

    // Zoom tightly into rectangle on incident switch
    handleFitBbox();

    const t = setTimeout(() => {
      map.invalidateSize();
    }, 200);

    return () => clearTimeout(t);
  }, [incident, showBbox, showMarkers, handleFitBbox]);

  const coords = incident?.primary_coordinates;
  const latStr = coords?.latitude != null ? coords.latitude.toFixed(4) : '--';
  const lonStr = coords?.longitude != null ? coords.longitude.toFixed(4) : '--';

  return (
    <section className="hero-map-slab">
      <article className="map-card-wrapper">
        <div className="map-control-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span className="map-title">Area of Interest (AOI) & High-Resolution Satellite Footprint</span>
            <span className="live-pulse-badge">
              <span className="pulse-dot"></span>
              <span>Copernicus &middot; USGS &middot; NASA Telemetry</span>
            </span>
          </div>
          <div className="map-actions">
            <button
              type="button"
              className={`map-chip-btn ${basemap === 'dark' ? 'active' : ''}`}
              onClick={() => handleBasemapChange('dark')}
            >
              Dark
            </button>
            <button
              type="button"
              className={`map-chip-btn ${basemap === 'satellite' ? 'active' : ''}`}
              onClick={() => handleBasemapChange('satellite')}
            >
              Satellite
            </button>
            <button
              type="button"
              className={`map-chip-btn ${basemap === 'osm' ? 'active' : ''}`}
              onClick={() => handleBasemapChange('osm')}
            >
              Streets
            </button>
            <span style={{ color: 'var(--border-subtle)', margin: '0 4px' }}>|</span>
            <button
              type="button"
              className={`map-chip-btn ${showBbox ? 'active' : ''}`}
              onClick={() => setShowBbox((prev) => !prev)}
            >
              AOI Box
            </button>
            <button
              type="button"
              className={`map-chip-btn ${showMarkers ? 'active' : ''}`}
              onClick={() => setShowMarkers((prev) => !prev)}
            >
              Pin
            </button>
            <button
              type="button"
              className="map-chip-btn"
              onClick={handleFitBbox}
              title="Zoom tightly into AOI rectangle"
            >
              Recenter AOI
            </button>
          </div>
        </div>

        {/* Floating Telemetry HUD Overlay */}
        <div className="map-floating-overlay">
          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
            {incident?.location || incident?.original_query || 'Global Map'}
          </span>
          <span style={{ margin: '0 6px', color: 'var(--text-tertiary)' }}>&bull;</span>
          <span style={{ fontFamily: 'var(--font-mono)', color: '#60a5fa' }}>
            Lat {latStr}, Lon {lonStr}
          </span>
        </div>

        {/* Leaflet Map DOM Node */}
        <div id="disaster-map" ref={mapContainerRef}></div>
      </article>
    </section>
  );
}
