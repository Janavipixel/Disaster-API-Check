import React from 'react';

export default function GroundTruthNotice() {
  return (
    <div
      style={{
        fontSize: '0.76rem',
        color: 'var(--text-tertiary)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: '14px 16px',
        lineHeight: 1.5,
      }}
    >
      <b style={{ color: 'var(--text-secondary)' }}>Ground Truth Boundary:</b> Media reports and
      humanitarian agency figures provide provisional situational context. Definitive physical damage and flood
      inundation perimeters must be validated against calibrated multi-temporal satellite radar backscatter and optical
      spectral observations.
    </div>
  );
}
