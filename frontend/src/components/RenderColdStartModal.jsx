import React, { useEffect, useState } from 'react';

export default function RenderColdStartModal({ isOpen, onClose, isLive = false }) {
  const [countdown, setCountdown] = useState(60);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);

    // Simple 60s countdown timer to inform user during Render free-tier container boot
    const timer = setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      clearInterval(timer);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="render-notice-overlay"
      id="render-cold-start-modal-overlay"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(2, 6, 23, 0.88)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        padding: '20px',
        animation: 'fadeIn 0.25s ease-out',
      }}
      onClick={onClose}
    >
      <div
        className="render-notice-card"
        id="render-cold-start-card"
        style={{
          width: '100%',
          maxWidth: '620px',
          background: 'linear-gradient(145deg, #0d1527, #030712)',
          border: '1px solid rgba(245, 158, 11, 0.45)',
          borderRadius: '20px',
          padding: '28px 32px',
          boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.85), 0 0 45px rgba(245, 158, 11, 0.2)',
          color: '#f8fafc',
          position: 'relative',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Dismiss Button */}
        <button
          type="button"
          id="btn-close-render-warning"
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '18px',
            right: '18px',
            background: 'rgba(255, 255, 255, 0.08)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '50%',
            width: '36px',
            height: '36px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#94a3b8',
            cursor: 'pointer',
            fontSize: '16px',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = '#ffffff';
            e.currentTarget.style.background = 'rgba(255, 255, 255, 0.16)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = '#94a3b8';
            e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
          }}
          title="Close warning (Esc)"
          aria-label="Close Notice"
        >
          ✕
        </button>

        {/* Warning Badge & Header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px', marginBottom: '20px' }}>
          <div
            style={{
              width: '52px',
              height: '52px',
              borderRadius: '16px',
              background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.25), rgba(217, 119, 6, 0.15))',
              border: '1px solid rgba(245, 158, 11, 0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '28px',
              flexShrink: 0,
              boxShadow: '0 0 20px rgba(245, 158, 11, 0.25)',
            }}
          >
            ⚠️
          </div>
          <div>
            <div
              style={{
                fontSize: '0.72rem',
                fontWeight: 800,
                color: '#fbbf24',
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                marginBottom: '4px',
              }}
            >
              Notice &bull; Backend Instance Deployment
            </div>
            <h2
              style={{
                fontSize: '1.4rem',
                fontWeight: 800,
                color: '#ffffff',
                margin: 0,
                letterSpacing: '-0.02em',
                lineHeight: '1.25',
              }}
            >
              Backend Is Deployed On Render
            </h2>
            <div style={{ fontSize: '0.85rem', color: '#f59e0b', fontWeight: 600, marginTop: '2px' }}>
              Please wait ~50&ndash;60 seconds for the free instance to spin up
            </div>
          </div>
        </div>

        {/* Body Description */}
        <div style={{ fontSize: '0.88rem', lineHeight: '1.65', color: '#cbd5e1', marginBottom: '22px' }}>
          <p style={{ margin: '0 0 14px 0' }}>
            The <strong>FastAPI &amp; Copernicus Sentinel-1 radar backend</strong> is hosted on Render’s free tier. Inactivity causes free instances to sleep; on the first query or site load, Render requires about <strong>1 minute</strong> to allocate a server instance and boot the container.
          </p>

          {/* Live Status Tracker Box */}
          <div
            style={{
              background: isLive ? 'rgba(34, 197, 94, 0.12)' : 'rgba(245, 158, 11, 0.1)',
              border: isLive ? '1px solid rgba(34, 197, 94, 0.4)' : '1px solid rgba(245, 158, 11, 0.35)',
              borderRadius: '12px',
              padding: '14px 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '14px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span
                style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  background: isLive ? '#22c55e' : '#f59e0b',
                  boxShadow: isLive ? '0 0 12px #22c55e' : '0 0 12px #f59e0b',
                  animation: 'pulse 1.5s infinite',
                }}
              />
              <span style={{ fontSize: '0.86rem', fontWeight: 700, color: isLive ? '#4ade80' : '#fbbf24' }}>
                {isLive ? 'Backend Online & Operational (Ready)' : 'Instance Spinning Up on Render...'}
              </span>
            </div>
            {!isLive && (
              <span style={{ fontSize: '0.78rem', fontFamily: 'monospace', color: '#94a3b8', background: 'rgba(0,0,0,0.3)', padding: '4px 8px', borderRadius: '6px' }}>
                {countdown > 0 ? `~${countdown}s remaining` : 'Ready any moment'}
              </span>
            )}
          </div>

          {/* Reassurance Callout */}
          <div
            style={{
              background: 'rgba(56, 189, 248, 0.08)',
              border: '1px solid rgba(56, 189, 248, 0.22)',
              borderRadius: '12px',
              padding: '12px 16px',
              fontSize: '0.8rem',
              color: '#93c5fd',
              lineHeight: '1.5',
            }}
          >
            🚀 <strong>Offline Benchmarks Ready Immediately:</strong> Even while the Render instance is spinning up, all 4 verified disaster scenarios (<strong>Kerala Floods</strong>, <strong>Nepal Landslide</strong>, <strong>Lucknow Gomti River</strong>, and <strong>California Wildfire</strong>) along with 20-meter SAR change rasters and split-swipe comparison sliders work right now on Vercel CDN!
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
            Press <kbd style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px', color: '#94a3b8' }}>Esc</kbd> or click outside to dismiss
          </span>
          <button
            type="button"
            id="btn-dismiss-render-warning"
            onClick={onClose}
            style={{
              background: 'linear-gradient(135deg, #f59e0b, #d97706)',
              border: 'none',
              borderRadius: '10px',
              padding: '11px 24px',
              color: '#000000',
              fontWeight: 800,
              fontSize: '0.9rem',
              cursor: 'pointer',
              boxShadow: '0 4px 16px rgba(245, 158, 11, 0.35)',
              transition: 'transform 0.15s ease, box-shadow 0.15s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-1px)';
              e.currentTarget.style.boxShadow = '0 6px 20px rgba(245, 158, 11, 0.5)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(245, 158, 11, 0.35)';
            }}
          >
            Understood &bull; Explore Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
