# 🛰️ Rakhshak (रक्षक)
### Satellite Radar & Multi-Agency AI Disaster Intelligence Platform

[![Vercel Frontend](https://img.shields.io/badge/Frontend-Vercel-black?style=flat&logo=vercel)](https://vercel.com)
[![Render Backend](https://img.shields.io/badge/Backend-Render-46E3B7?style=flat&logo=render)](https://render.com)
[![Copernicus Sentinel-1](https://img.shields.io/badge/Radar-Copernicus%20Sentinel--1-003399?style=flat)](https://dataspace.copernicus.eu/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Rakhshak** unites all-weather, cloud-penetrating **Copernicus Sentinel-1 Synthetic Aperture Radar (SAR)** imagery with a source-verified AI engine and multi-agency telemetry. It enables emergency responders and disaster management authorities to rapidly assess disaster footprints (floods, landslides, wildfires, earthquakes) down to **20-meter resolution**, day or night.

---
## Problem Statement

Natural disasters such as floods, earthquakes, and cyclones can cause severe damage to infrastructure, communities, and essential services. However, identifying affected areas and assessing changes quickly remains a major challenge due to delays in ground-based assessments and the complexity of satellite image analysis.

There is a need for an integrated disaster intelligence platform that combines real-time disaster data, satellite imagery, and automated change detection to identify potentially affected regions. The platform aims to help users visualize disaster events, compare pre-disaster and post-disaster satellite imagery, map detected changes, and generate actionable insights to support faster, data-driven disaster response and recovery planning.

## ⚡ Architecture & Deployment

The platform is split into a cloud-native decoupled architecture:

```
┌────────────────────────────────────────────────────────┐
│  Frontend (Vercel)                                     │
│  • React 18 + Vite + Three.js Ambient Globe            │
│  • Leaflet Multi-Temporal SAR Split Swipe Slider       │
│  • Offline Benchmarks (Kerala, Nepal, Lucknow, CampFire)│
└──────────────────────────┬─────────────────────────────┘
                           │ HTTPS REST / Live Telemetry
┌──────────────────────────▼─────────────────────────────┐
│  Backend (Render)                                      │
│  • FastAPI Service (`run_server.py`)                   │
│  • Copernicus Data Space Ecosystem (CDSE) Ingestion    │
│  • Multi-Source Telemetry (NASA, USGS, GDACS, UN OCHA) │
└────────────────────────────────────────────────────────┘
```

> [!NOTE]
> **Render Free-Tier Cold Starts:**
> The live FastAPI container runs on Render's free tier. Idle instances automatically sleep; booting up on the first live query takes **~50–60 seconds**.
> 
> All 4 benchmark scenarios, SAR change rasters, and split-swipe comparison sliders are bundled directly on Vercel CDN and operate **instantaneously without waiting for the backend**.

---

## 🌟 Key Features

- **All-Weather Vision (SAR):** Bypasses monsoon cloud cover and smoke using C-Band radar backscatter (VV + VH polarizations).
- **Automated Change Detection:** Computes log-ratio difference rasters between pre- and post-disaster orbits to calculate inundated surface area in km² and hectares.
- **Split-Swipe Comparison Slider:** Drag-to-compare interactive Leaflet viewer with synchronized zoom, pan, and coordinate tracking.
- **Multi-Agency Consensus:** Fuses real-time feeds from NASA FIRMS, USGS Earthquake Hazards, UN OCHA ReliefWeb, and GDACS alerts.
- **Offline Resilient:** 100% operational in zero-connectivity field conditions with local benchmark baselines and ChromaDB vector store fallback.

---

## 🚀 Quick Start (Local Development)

### 1. Prerequisites
- **Node.js** (v18+)
- **Python** (v3.10+)

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
# Dashboard opens on http://localhost:5173
```

### 3. Backend Setup
```bash
# In the repository root
python -m venv venv
# Windows: venv\Scripts\activate | Linux/macOS: source venv/bin/activate
pip install -r "Disaster API/requirements.txt"
python run_server.py
# FastAPI Swagger docs on http://localhost:8000/docs
```

### 4. Configuration
Copy `.env.example` to `.env` and configure your API keys (all optional with graceful fallbacks):
```ini
CDSE_CLIENT_ID=your_copernicus_client_id
CDSE_CLIENT_SECRET=your_copernicus_client_secret
VITE_API_URL=https://your-render-service.onrender.com
```

---

## 🏛️ Verified Benchmark Scenarios

| Scenario | Location | Sensor & Orbit | Impact Detected |
|---|---|---|---|
| **Kerala Floods (2018)** | Periyar & Alappuzha, IND | Sentinel-1 SAR Orbit 163 | 40.71 km² (4,070.9 ha) standing water |
| **Nepal Landslide (2024)** | Trishuli Basin, NPL | Sentinel-1 SAR Orbit 085 | 18.40 km² debris displacement |
| **Lucknow Inundation (2023)** | Gomti Basin, IND | Sentinel-1 SAR Orbit 017 | 12.60 km² riparian overflow |
| **Camp Fire (2018)** | Paradise, California, USA | Sentinel-1 SAR Orbit 137 | Severe backscatter decimation |

---

## 🔒 Confidentiality & Deployment Safety
- Backend Dockerfile is production-hardened for Render (`PORT` injection compliant).
- Frontend is configured for zero-configuration Vercel deployment with SPA rewrites (`vercel.json`).
- Repository hygiene: `.env`, `.venv`, and sensitive credentials strictly gitignored.
