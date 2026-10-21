import React from 'react';

export default function FIRMSPane({ incident }) {
  const firms = incident?.firms;
  const detections = firms?.matched_detections || [];

  if (!firms || detections.length === 0) {
    return (
      <div style={{ color: 'var(--text-tertiary)', fontSize: '0.86rem', padding: '16px 0', lineHeight: 1.6 }}>
        <p style={{ marginBottom: '6px' }}>
          <b>NASA FIRMS Satellite Telemetry:</b> No high-confidence active thermal fire/flare anomalies detected in this AOI.
        </p>
        <span style={{ fontSize: '0.78rem' }}>
          FIRMS scans thermal radiance via VIIRS (S-NPP, NOAA-20, NOAA-21) and MODIS (Terra & Aqua) sensors for thermal hotspots.
        </span>
      </div>
    );
  }

  return (
    <div className="telemetry-stack">
      <div style={{ marginBottom: '12px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
        <span>Sensor Instrument: <b style={{ color: '#f87171' }}>{firms.sensor || 'VIIRS / MODIS Satellite Radiometer'}</b></span>
        <span style={{ margin: '0 8px' }}>&bull;</span>
        <span>Active Thermal Detections: <b style={{ color: '#fbbf24' }}>{detections.length} hotspots</b></span>
      </div>

      {detections.map((det, idx) => (
        <div key={idx} className="verification-entry">
          <div className="verification-entry-header">
            <span className="verification-topic" style={{ color: '#f87171' }}>
              Thermal Hotspot #{idx + 1} &mdash; Lat {det.latitude?.toFixed(4)}, Lon {det.longitude?.toFixed(4)}
            </span>
            <span className="verification-status-pill status-conflicting">
              FRP: {det.frp != null ? `${det.frp} MW` : 'N/A'}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '8px', fontSize: '0.78rem', marginTop: '6px' }}>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Confidence:</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>{det.confidence || 'Nominal'}</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Acquisition Date:</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>{det.acq_date || '--'}</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Acquisition Time:</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>{det.acq_time ? `${det.acq_time} UTC` : '--'}</b>
            </div>
            <div>
              <span style={{ color: 'var(--text-tertiary)' }}>Pass:</span>{' '}
              <b style={{ color: 'var(--text-primary)' }}>{det.daynight === 'D' ? 'Day Orbit' : 'Night Orbit'}</b>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
