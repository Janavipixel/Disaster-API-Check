/**
 * Mock Incident Datasets matching the exact Pydantic schema of UnifiedIncidentReport from Disaster API.
 * These provide high-fidelity offline demonstrations for each hazard category.
 */

export const MOCK_INCIDENTS = {
  "kerala": {
    id: "kerala",
    original_query: "Kerala floods August 2018",
    disaster_type: "floods",
    hazard_icon: "🌊",
    location: "Kerala, India",
    incident_date_str: "August 2018",
    query_window_start: "2018-08-01",
    query_window_end: "2018-08-31",
    severity_level: "Orange",
    severity_score: 2.0,
    glide: "FL-2018-000134-IND",
    primary_coordinates: {
      latitude: 9.9190,
      longitude: 76.4030,
      depth_km: null,
      source: "GDACS Alert Centroid (Flood in India)",
      coordinate_type: "centroid",
      coordinate_label: "GDACS Event Centroid",
      disclaimer: "Point estimate only; does not define spatial perimeter, flood inundation boundary, or disaster footprint."
    },
    bbox: [76.2, 9.8, 76.6, 10.2], // [min_lon, min_lat, max_lon, max_lat]
    sources_queried: ["GDACS Disaster Alerts", "ReliefWeb Humanitarian Reports", "Tavily Web Intelligence"],
    sources_succeeded: ["GDACS Disaster Alerts", "ReliefWeb Humanitarian Reports", "Tavily Web Intelligence"],
    sources_failed: {},
    usgs: {
      queried: false,
      status: "not_applicable",
      matched_events: [],
      error_message: "USGS Earthquake Catalog is specialized for seismic hazards; skipped for this disaster type."
    },
    gdacs: {
      queried: true,
      status: "success",
      alert_level: "Orange",
      alert_score: 2.0,
      matched_events: [
        {
          event_id: "1000212",
          episode_id: "2",
          name: "Flood in India (Kerala)",
          glide: "2018-000134",
          alert_level: "Orange",
          alert_score: 2.0,
          duration: "2018-08-10 to 2018-09-24",
          centroid: { lat: 9.9190, lon: 76.4030 },
          severity_text: "Severe monsoonal inundation across 14 districts",
          affected_population: "~5.4 million people exposed",
          report_url: "https://www.gdacs.org/report.aspx?eventid=1000212&episodeid=2&eventtype=FL"
        }
      ]
    },
    reliefweb: {
      queried: true,
      status: "success",
      matched_reports: [
        {
          id: "2754629",
          title: "India: Floods in Kerala - Situation Report No. 1 (as of 19 August 2018)",
          source: "UN OCHA / Inter-Agency Coordination",
          published_date: "2018-08-19",
          url: "https://reliefweb.int/report/india/india-floods-kerala-situation-report-no-1-19-august-2018",
          summary: "Severe flooding and landslides hit all 14 districts of Kerala after intense monsoon downpours. Over 1.4 million people displaced into 3,879 relief camps. State water reservoirs opened 35 dams."
        },
        {
          id: "2759144",
          title: "Kerala Floods: Joint Rapid Needs Assessment August 2018",
          source: "Sphere India",
          published_date: "2018-08-27",
          url: "https://reliefweb.int/report/india/kerala-floods-joint-rapid-needs-assessment-august-2018",
          summary: "Assessment of WASH, shelter, health, and livelihood recovery needs across Wayanad, Idukki, Alappuzha, and Ernakulam districts."
        }
      ]
    },
    firms: {
      queried: false,
      status: "not_applicable",
      matched_detections: [],
      error_message: "NASA FIRMS Active Fire is specialized for thermal anomaly monitoring; skipped."
    },
    tavily: {
      queried: true,
      status: "success",
      article_count: 5,
      synthesized_summary: "In August 2018, the Indian state of Kerala experienced its worst flooding in nearly a century due to unusually heavy monsoon rainfall (estimated 164% above normal). Torrential downpours filled 35 of the state's major reservoirs to capacity, forcing unprecedented dam water releases that inundated coastal and riverine settlements.",
      verified_claims: [
        {
          topic: "Rainfall Measurement",
          claim: "Peak rainfall recorded at 3,521 mm over monsoon season (164% above normal).",
          status: "corroborated",
          sources: [
            { domain: "thehindu.com", quote: "monsoon season recorded 164% surplus rain" },
            { domain: "imd.gov.in", quote: "cumulative monsoon rainfall exceeded 3,500 mm" }
          ],
          explanation: "Corroborated across India Meteorological Department telemetry and major state dispatches."
        },
        {
          topic: "Population Displacement",
          claim: "Over 1.4 million residents sheltered across relief camps.",
          status: "corroborated",
          sources: [
            { domain: "reliefweb.int", quote: "1.4 million people displaced into 3,879 relief camps" },
            { domain: "ndtv.com", quote: "more than 1.4 million people took refuge in relief camps" }
          ],
          explanation: "Government disaster relief administration consensus."
        },
        {
          topic: "Casualty Discrepancy",
          claim: "Fatalities cited between 370 (early dispatches) and 483 (final official assembly report).",
          status: "conflicting",
          sources: [
            { domain: "bbc.com", quote: "at least 370 people have died in Kerala" },
            { domain: "thehindu.com", quote: "official death toll confirmed at 483" }
          ],
          explanation: "Early operational media dispatches contrasted against finalized legislative inquiries."
        }
      ]
    },
    satellite_layers: {
      sensor: "Sentinel-1A SAR C-Band (IW GRD)",
      orbit: "Relative Orbit 165 (Descending)",
      pre_event_date: "2018-08-09",
      post_event_date: "2018-08-21",
      detected_inundation_area_km2: 40.71,
      change_metric: "VV Backscatter Drop < -3.25 dB (Specular Water Reflection)",
      pre_preview_url: "/api/copernicus/runs/kerala_2018-08-10/images/pre_vv_db.png",
      post_preview_url: "/api/copernicus/runs/kerala_2018-08-10/images/post_vv_db.png",
      change_overlay_url: "/api/copernicus/runs/kerala_2018-08-10/images/change_mask_overlay.png",
      delta_url: "/api/copernicus/runs/kerala_2018-08-10/images/delta_vv_db.png",
      histogram_url: "/api/copernicus/runs/kerala_2018-08-10/images/delta_vv_histogram.png",
      summary_url: "/api/copernicus/runs/kerala_2018-08-10/images/summary_panel.png",
      run_id: "kerala_2018-08-10"
    }
  },

  "lucknow": {
    id: "lucknow",
    original_query: "Lucknow Gomti floods October 2026",
    disaster_type: "floods",
    hazard_icon: "🌊",
    location: "Lucknow, Uttar Pradesh, India",
    incident_date_str: "October 1, 2026",
    query_window_start: "2026-09-15",
    query_window_end: "2026-10-15",
    severity_level: "Yellow",
    severity_score: 1.5,
    glide: "FL-2026-000088-IND",
    primary_coordinates: {
      latitude: 26.8500,
      longitude: 80.9500,
      depth_km: null,
      source: "Gomti River Basin Hydrological Center",
      coordinate_type: "centroid",
      coordinate_label: "Lucknow Urban AOI Centroid",
      disclaimer: "Point estimate only; does not define spatial perimeter, flood inundation boundary, or disaster footprint."
    },
    bbox: [80.85, 26.75, 81.05, 26.95],
    sources_queried: ["GDACS Disaster Alerts", "ReliefWeb Humanitarian Reports", "Tavily Web Intelligence"],
    sources_succeeded: ["GDACS Disaster Alerts", "ReliefWeb Humanitarian Reports", "Tavily Web Intelligence"],
    sources_failed: {},
    usgs: {
      queried: false,
      status: "not_applicable",
      matched_events: [],
      error_message: "USGS Earthquake Catalog is specialized for seismic hazards; skipped for this disaster type."
    },
    gdacs: {
      queried: true,
      status: "success",
      alert_level: "Yellow",
      alert_score: 1.5,
      matched_events: [
        {
          event_id: "1000998",
          episode_id: "1",
          name: "Flood in India (Lucknow Basin)",
          glide: "2026-000088",
          alert_level: "Yellow",
          alert_score: 1.5,
          duration: "2026-09-28 to 2026-10-10",
          centroid: { lat: 26.85, lon: 80.95 },
          severity_text: "Monsoonal river overflow along urban Gomti embankment",
          affected_population: "~420,000 residents in riverine lowlands",
          report_url: "https://www.gdacs.org/report.aspx?eventid=1000998"
        }
      ]
    },
    reliefweb: {
      queried: true,
      status: "success",
      matched_reports: [
        {
          id: "3129841",
          title: "India: Uttar Pradesh Monsoon Overflow & Urban Flood Preparedness Report",
          source: "State Disaster Management Authority / UN OCHA",
          published_date: "2026-10-02",
          url: "https://reliefweb.int/report/india/uttar-pradesh-monsoon-overflow-2026",
          summary: "Water discharge in Gomti river reaches critical warning thresholds. Low-lying riverfront zones inundated."
        }
      ]
    },
    firms: {
      queried: false,
      status: "not_applicable",
      matched_detections: [],
      error_message: "NASA FIRMS Active Fire is specialized for thermal anomaly monitoring; skipped."
    },
    tavily: {
      queried: true,
      status: "success",
      article_count: 4,
      synthesized_summary: "In early October 2026, persistent catchment downpours caused significant surge in the Gomti River basin, impacting low-lying urban sectors of Lucknow. Municipal disaster rescue units initiated perimeter flood barricading and satellite-guided drainage pumping.",
      verified_claims: [
        {
          topic: "River Stage",
          claim: "Gomti water level measured near 109.8 meters danger mark.",
          status: "corroborated",
          sources: [
            { domain: "cwc.gov.in", quote: "Gomti stage within 0.5m of danger level" },
            { domain: "timesofindia.indiatimes.com", quote: "barricades deployed along riverfront" }
          ],
          evidence_explanation: "Verified by Central Water Commission monitoring stations."
        }
      ]
    },
    satellite_layers: {
      sensor: "Sentinel-1D SAR C-Band (IW GRD)",
      orbit: "Relative Orbit 165 (Descending)",
      pre_event_date: "2026-09-27",
      post_event_date: "2026-10-09",
      detected_inundation_area_km2: 18.4,
      change_metric: "VV Backscatter Drop < -3.2 dB (Specular Water Reflection)",
      pre_preview_url: "/api/copernicus/runs/lucknow_2026-10-01/images/pre_vv_db.png",
      post_preview_url: "/api/copernicus/runs/lucknow_2026-10-01/images/post_vv_db.png",
      change_overlay_url: "/api/copernicus/runs/lucknow_2026-10-01/images/change_mask_overlay.png",
      delta_url: "/api/copernicus/runs/lucknow_2026-10-01/images/delta_vv_db.png",
      histogram_url: "/api/copernicus/runs/lucknow_2026-10-01/images/delta_vv_histogram.png",
      summary_url: "/api/copernicus/runs/lucknow_2026-10-01/images/summary_panel.png",
      run_id: "lucknow_2026-10-01"
    }
  },

  "turkey": {
    id: "turkey",
    original_query: "Turkey earthquake February 6 2023",
    disaster_type: "earthquake",
    hazard_icon: "🌋",
    location: "Kahramanmaraş / Gaziantep, Türkiye",
    incident_date_str: "February 6, 2023",
    query_window_start: "2023-02-06",
    query_window_end: "2023-02-08",
    severity_level: "Red",
    severity_score: 3.0,
    glide: "EQ-2023-000015-TUR",
    primary_coordinates: {
      latitude: 37.2256,
      longitude: 37.0143,
      depth_km: 10.0,
      source: "USGS Earthquake Catalog (Pazarcik earthquake, Kahramanmaras sequence)",
      coordinate_type: "epicenter",
      coordinate_label: "USGS Earthquake Epicenter",
      disclaimer: "Point epicenter does NOT represent the full fault rupture zone (~300 km) or surface shake footprint."
    },
    bbox: [36.2, 36.5, 38.5, 38.6],
    sources_queried: ["USGS Earthquake Catalog", "GDACS Disaster Alerts", "ReliefWeb Humanitarian Reports", "Tavily Web Intelligence"],
    sources_succeeded: ["USGS Earthquake Catalog", "GDACS Disaster Alerts", "ReliefWeb Humanitarian Reports", "Tavily Web Intelligence"],
    sources_failed: {},
    usgs: {
      queried: true,
      status: "success",
      matched_events: [
        {
          event_id: "us6000jllz",
          magnitude: 7.8,
          magnitude_type: "mww",
          place: "Pazarcik earthquake, Kahramanmaras sequence",
          origin_time: "2023-02-06T01:17:34.342Z",
          coordinates: { lat: 37.2256, lon: 37.0143, depth_km: 10.0 },
          alert_level: "red",
          mmi: 9.1,
          felt_reports: 2845,
          significance: 2280,
          catalog_url: "https://earthquake.usgs.gov/earthquakes/eventpage/us6000jllz"
        },
        {
          event_id: "us6000jlqa",
          magnitude: 7.5,
          magnitude_type: "mww",
          place: "Elbistan earthquake, Kahramanmaras sequence",
          origin_time: "2023-02-06T10:24:48.811Z",
          coordinates: { lat: 38.0106, lon: 37.1962, depth_km: 7.4 },
          alert_level: "red",
          mmi: 8.8,
          catalog_url: "https://earthquake.usgs.gov/earthquakes/eventpage/us6000jlqa"
        }
      ]
    },
    gdacs: {
      queried: true,
      status: "success",
      alert_level: "Red",
      alert_score: 3.0,
      matched_events: [
        {
          event_id: "1357372",
          episode_id: "1487096",
          name: "Earthquake in Türkiye (M7.8)",
          glide: "EQ-2023-000015-TUR",
          alert_level: "Red",
          alert_score: 3.0,
          duration: "2023-02-06 01:17 UTC",
          centroid: { lat: 37.1736, lon: 37.0320 },
          severity_text: "Catastrophic East Anatolian Fault rupture",
          affected_population: "13.5M in Turkey, 8.8M in Syria",
          report_url: "https://www.gdacs.org/report.aspx?eventid=1357372"
        }
      ]
    },
    reliefweb: {
      queried: true,
      status: "success",
      matched_reports: [
        {
          id: "3935293",
          title: "Türkiye / Syria: Earthquake Flash Appeal (February 2023)",
          source: "UN OCHA",
          published_date: "2023-02-14",
          url: "https://reliefweb.int/report/turkiye/turkiye-2023-earthquakes-situation-report-no-1",
          summary: "Flash appeal launching $1 billion in emergency assistance for 5.2 million affected people across 11 provinces."
        }
      ]
    },
    firms: {
      queried: false,
      status: "not_applicable",
      matched_detections: [],
      error_message: "NASA FIRMS is specialized for thermal anomalies; skipped."
    },
    tavily: {
      queried: true,
      status: "success",
      article_count: 6,
      synthesized_summary: "On 6 February 2023, two ultra-destructive earthquakes with moment magnitudes of 7.8 and 7.5 struck southern and central Turkey and northern Syria. The seismic sequence ruptured segments of the East Anatolian Fault and Çardak Fault, causing massive structural collapse across Gaziantep, Hatay, Kahramanmaraş, and Aleppo.",
      verified_claims: [
        {
          topic: "Magnitude and Fault Rupture",
          claim: "Primary M7.8 rupture followed 9 hours later by M7.5 doublet.",
          status: "corroborated",
          sources: [
            { domain: "usgs.gov", quote: "M 7.8 Pazarcik earthquake" },
            { domain: "reuters.com", quote: "a second quake measuring 7.5 hit the region nine hours later" }
          ],
          explanation: "Validated by global seismic network telemetry and official Turkish AFAD recordings."
        },
        {
          topic: "Casualty Toll",
          claim: "Combined death toll surpassed 53,000 in Turkey and 5,900 in Syria.",
          status: "corroborated",
          sources: [
            { domain: "apnews.com", quote: "official death toll in Turkey reached over 50,000" },
            { domain: "reliefweb.int", quote: "combined fatalities exceeding 59,000 across Turkey and Syria" }
          ],
          explanation: "Corroborated by UN OCHA and Turkish Ministry of Interior confirmations."
        }
      ]
    },
    satellite_layers: {
      sensor: "Sentinel-1 InSAR Coherence & Optical Sentinel-2",
      orbit: "Relative Orbit 14 (Ascending)",
      pre_event_date: "2023-01-28",
      post_event_date: "2023-02-09",
      detected_inundation_area_km2: null,
      change_metric: "Surface Rupture Offset up to 7.2 meters; InSAR Coherence Loss",
      pre_preview_url: null,
      post_preview_url: null,
      run_id: null,
      status: "not_applicable"
    }
  },

  "california": {
    id: "california",
    original_query: "Camp Fire California November 2018",
    disaster_type: "wildfire",
    hazard_icon: "🔥",
    location: "Butte County, California, USA",
    incident_date_str: "November 2018",
    query_window_start: "2018-11-08",
    query_window_end: "2018-11-25",
    severity_level: "Red",
    severity_score: 2.8,
    glide: "WF-2018-000201-USA",
    primary_coordinates: {
      latitude: 39.8105,
      longitude: -121.4372,
      depth_km: null,
      source: "NASA FIRMS VIIRS Active Fire Detection Cluster",
      coordinate_type: "thermal_centroid",
      coordinate_label: "FIRMS Thermal Anomaly Centroid",
      disclaimer: "Thermal centroid indicates primary high-temperature sensor anomaly; boundary requires multi-temporal burn scar mapping."
    },
    bbox: [-121.7, 39.6, -121.3, 40.0],
    sources_queried: ["NASA FIRMS Active Fire", "GDACS Disaster Alerts", "Tavily Web Intelligence"],
    sources_succeeded: ["NASA FIRMS Active Fire", "GDACS Disaster Alerts", "Tavily Web Intelligence"],
    sources_failed: {},
    usgs: {
      queried: false,
      status: "not_applicable",
      matched_events: [],
      error_message: "Seismic catalog skipped for wildfire hazard."
    },
    gdacs: {
      queried: true,
      status: "success",
      alert_level: "Orange",
      alert_score: 2.1,
      matched_events: [
        {
          event_id: "1000301",
          episode_id: "1",
          name: "Wildfire in United States (Camp Fire)",
          glide: "WF-2018-000201-USA",
          alert_level: "Orange",
          alert_score: 2.1,
          duration: "2018-11-08 to 2018-11-25",
          centroid: { lat: 39.8105, lon: -121.4372 },
          severity_text: "Catastrophic wildland-urban interface conflagration",
          affected_population: "~50,000 displaced",
          report_url: "https://www.gdacs.org/report.aspx?eventid=1000301"
        }
      ]
    },
    reliefweb: {
      queried: true,
      status: "success",
      matched_reports: [
        {
          id: "2871101",
          title: "USA: California Wildfires (Camp & Woolsey Fires) - November 2018",
          source: "Red Cross / ReliefWeb",
          published_date: "2018-11-12",
          url: "https://reliefweb.int/report/united-states-america/california-wildfires-november-2018",
          summary: "Camp Fire destroyed the town of Paradise in Butte County. Over 18,000 structures obliterated."
        }
      ]
    },
    firms: {
      queried: true,
      status: "success",
      satellite_source: "VIIRS_SNPP_NRT",
      total_detections_found: 412,
      matched_detections: [
        {
          latitude: 39.812,
          longitude: -121.439,
          brightness: 367.4,
          scan: 0.38,
          track: 0.36,
          acq_date: "2018-11-08",
          acq_time: "1042",
          satellite: "N",
          confidence: "nominal",
          frp: 284.1,
          daynight: "D"
        },
        {
          latitude: 39.795,
          longitude: -121.492,
          brightness: 382.1,
          scan: 0.39,
          track: 0.36,
          acq_date: "2018-11-08",
          acq_time: "1042",
          satellite: "N",
          confidence: "high",
          frp: 512.6,
          daynight: "D"
        }
      ]
    },
    tavily: {
      queried: true,
      status: "success",
      article_count: 5,
      synthesized_summary: "Ignited on November 8, 2018, by faulty electrical transmission lines in Butte County, the Camp Fire exploded westward through bone-dry vegetation driven by 50 mph Jarbo winds. It became the deadliest and most destructive wildfire in California history.",
      verified_claims: [
        {
          topic: "Burn Extent and Destruction",
          claim: "153,336 acres burned and 18,804 structures destroyed.",
          status: "corroborated",
          sources: [
            { domain: "fire.ca.gov", quote: "153,336 acres and 18,804 structures" },
            { domain: "latimes.com", quote: "wiped out Paradise, destroying nearly 19,000 buildings" }
          ],
          explanation: "CAL FIRE official incident conclusion."
        },
        {
          topic: "Fatalities",
          claim: "85 civilian fatalities confirmed.",
          status: "corroborated",
          sources: [
            { domain: "bbc.com", quote: "death toll stands at 85" },
            { domain: "cbsnews.com", quote: "85 confirmed deaths in Camp Fire" }
          ],
          explanation: "Butte County Sheriff coroner verification."
        }
      ]
    },
    satellite_layers: {
      sensor: "Sentinel-2 MultiSpectral (Bands 12/8A/4 Burn Scar Index)",
      orbit: "Sentinel-2 Tile 10TEK",
      pre_event_date: "2018-10-31",
      post_event_date: "2018-11-15",
      detected_inundation_area_km2: null,
      change_metric: "Normalized Burn Ratio (NBR) Drop > 0.45",
      pre_preview_url: null,
      post_preview_url: null,
      run_id: null,
      status: "not_applicable"
    }
  },

  "mumbai": {
    id: "mumbai",
    original_query: "Mumbai floods July 2005",
    disaster_type: "floods",
    hazard_icon: "🌊",
    location: "Mumbai, Maharashtra, India",
    incident_date_str: "July 26, 2005",
    query_window_start: "2005-07-26",
    query_window_end: "2005-07-28",
    severity_level: "Red",
    severity_score: 2.9,
    glide: "FL-2005-000122-IND",
    primary_coordinates: {
      latitude: 19.0760,
      longitude: 72.8777,
      depth_km: null,
      source: "Geocoded Municipal Jurisdiction Centroid (Santacruz / Mithi River)",
      coordinate_type: "centroid",
      coordinate_label: "Municipal Incident Centroid",
      disclaimer: "Historical incident center; localized urban waterlogging throughout Salsette Island."
    },
    bbox: [72.7, 18.8, 73.2, 19.5],
    sources_queried: ["Tavily Web Intelligence", "GDACS Disaster Alerts"],
    sources_succeeded: ["Tavily Web Intelligence"],
    sources_failed: {},
    usgs: { queried: false, status: "not_applicable", matched_events: [] },
    gdacs: { queried: true, status: "historical_archive", alert_level: "Orange", alert_score: 2.0, matched_events: [] },
    reliefweb: { queried: true, status: "historical_archive", matched_reports: [] },
    firms: { queried: false, status: "not_applicable", matched_detections: [] },
    tavily: {
      queried: true,
      status: "success",
      article_count: 5,
      synthesized_summary: "On 26 July 2005, Mumbai was inundated by a catastrophic cloudburst where the Santacruz weather station recorded 944 mm (37.2 inches) of rain in 24 hours. Overflowing Mithi river and clogged stormwater outflows left the metropolitan transport network entirely paralyzed.",
      verified_claims: [
        {
          topic: "24-Hour Rainfall Record",
          claim: "944 mm rainfall in 24 hours (eighth heaviest recorded globally in a day).",
          status: "corroborated",
          sources: [
            { domain: "thehindu.com", quote: "Santacruz recorded 944 mm within 24 hours" },
            { domain: "wikipedia.org", quote: "944 millimetres in twenty-four hours" }
          ],
          explanation: "Corroborated across meteorological records with normalized metric unit equivalence."
        },
        {
          topic: "Casualty Scale",
          claim: "Total fatalities estimated at 1,094 across Mumbai and coastal Maharashtra.",
          status: "corroborated",
          sources: [
            { domain: "timesofindia.indiatimes.com", quote: "death toll officially estimated at 1,094" },
            { domain: "reuters.com", quote: "over 1,000 lives lost during July 26 deluge" }
          ],
          explanation: "Government Fact-Finding Committee on Mumbai Floods (Chitirale Committee Report)."
        }
      ]
    },
    satellite_layers: {
      sensor: "Historical Multi-Spectral & SAR Archives",
      orbit: "Historical Swath",
      pre_event_date: "2005-07-15",
      post_event_date: "2005-07-28",
      detected_inundation_area_km2: 120.4,
      change_metric: "Submerged Urban Impervious Surface Detection",
      pre_preview_url: "https://images.unsplash.com/photo-1570168007204-dfb528c6958f?auto=format&fit=crop&w=1200&q=80",
      post_preview_url: "https://images.unsplash.com/photo-1547683905-f686c993aae5?auto=format&fit=crop&w=1200&q=80"
    }
  }
};
