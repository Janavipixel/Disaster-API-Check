import React, { useState } from 'react';
import VerificationPane from './panes/VerificationPane.jsx';
import USGSPane from './panes/USGSPane.jsx';
import GDACSPane from './panes/GDACSPane.jsx';
import ReliefWebPane from './panes/ReliefWebPane.jsx';
import FIRMSPane from './panes/FIRMSPane.jsx';

export default function FeedsCard({ incident }) {
  const [activeTab, setActiveTab] = useState('tab-verification');

  return (
    <article className="surface-card feeds-card">
      <nav className="pills-nav-wrapper" role="tablist" aria-label="Disaster Intelligence Feeds">
        {/* Cross-Verification */}
        <button
          type="button"
          className={`nav-pill-btn org-btn-verify ${activeTab === 'tab-verification' ? 'active' : ''}`}
          onClick={() => setActiveTab('tab-verification')}
          role="tab"
          aria-selected={activeTab === 'tab-verification'}
          title="Multi-Source Intelligence Verification Matrix"
        >
          <div className="org-logo-frame">
            <svg className="org-logo-svg" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="28" height="28" rx="6" fill="#08182b" stroke="#1d4ed8" strokeWidth="1.2" />
              <path
                d="M14 4.5L6 8.5V14.5C6 19.5 9.5 24 14 25.5C18.5 24 22 19.5 22 14.5V8.5L14 4.5Z"
                fill="#1e3a8a"
                fillOpacity="0.5"
                stroke="#38bdf8"
                strokeWidth="1.4"
                strokeLinejoin="round"
              />
              <path
                d="M10 14.5L12.8 17.3L18.5 11"
                stroke="#38bdf8"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="14" cy="4.5" r="1.5" fill="#38bdf8" />
              <circle cx="6" cy="8.5" r="1.2" fill="#60a5fa" />
              <circle cx="22" cy="8.5" r="1.2" fill="#60a5fa" />
            </svg>
          </div>
          <div className="org-text-content">
            <div className="org-primary-name">Cross-Verification</div>
            <div className="org-sub-badge">Consensus Matrix</div>
          </div>
          <div className="org-active-indicator"></div>
        </button>

        {/* USGS Seismic */}
        <button
          type="button"
          className={`nav-pill-btn org-btn-usgs ${activeTab === 'tab-usgs' ? 'active' : ''}`}
          onClick={() => setActiveTab('tab-usgs')}
          role="tab"
          aria-selected={activeTab === 'tab-usgs'}
          title="United States Geological Survey - Real-time Seismic Telemetry"
        >
          <div className="org-logo-frame">
            <svg className="org-logo-svg" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="28" height="28" rx="6" fill="#032114" stroke="#005A32" strokeWidth="1.2" />
              <circle cx="14" cy="14" r="10.5" fill="#004d26" stroke="#16a34a" strokeWidth="0.8" />
              <text
                x="14"
                y="13.2"
                textAnchor="middle"
                fontFamily="'Inter', -apple-system, sans-serif"
                fontWeight="900"
                fontSize="6.4"
                fill="#ffffff"
                letterSpacing="-0.3px"
              >
                USGS
              </text>
              <path
                d="M6.5 18H9.5L11 15.5L12.5 20.5L14.2 16.2L15.8 19.2L17.2 18H21.5"
                stroke="#4ade80"
                strokeWidth="1.1"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="org-text-content">
            <div className="org-primary-name">USGS Seismic</div>
            <div className="org-sub-badge">Geological Survey</div>
          </div>
          <div className="org-active-indicator"></div>
        </button>

        {/* GDACS Alerts */}
        <button
          type="button"
          className={`nav-pill-btn org-btn-gdacs ${activeTab === 'tab-gdacs' ? 'active' : ''}`}
          onClick={() => setActiveTab('tab-gdacs')}
          role="tab"
          aria-selected={activeTab === 'tab-gdacs'}
          title="Global Disaster Alert and Coordination System (UN / European Commission)"
        >
          <div className="org-logo-frame">
            <svg className="org-logo-svg" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="28" height="28" rx="6" fill="#0a1224" stroke="#004B87" strokeWidth="1.2" />
              <circle cx="14" cy="14" r="10.5" fill="#002855" stroke="#38bdf8" strokeWidth="0.8" />
              <ellipse cx="14" cy="14" rx="5" ry="10.5" stroke="#38bdf8" strokeWidth="0.7" fill="none" opacity="0.8" />
              <line x1="3.5" y1="14" x2="24.5" y2="14" stroke="#38bdf8" strokeWidth="0.7" opacity="0.8" />
              <line x1="5.5" y1="9" x2="22.5" y2="9" stroke="#38bdf8" strokeWidth="0.6" strokeDasharray="1 1" opacity="0.7" />
              <line x1="5.5" y1="19" x2="22.5" y2="19" stroke="#38bdf8" strokeWidth="0.6" strokeDasharray="1 1" opacity="0.7" />
              <circle cx="16.5" cy="10.5" r="4.2" fill="none" stroke="#f97316" strokeWidth="0.9" opacity="0.7" />
              <circle cx="16.5" cy="10.5" r="2.2" fill="#ea580c" />
              <circle cx="16.5" cy="10.5" r="0.9" fill="#ffffff" />
            </svg>
          </div>
          <div className="org-text-content">
            <div className="org-primary-name">GDACS Alerts</div>
            <div className="org-sub-badge">UN & EC Alerts</div>
          </div>
          <div className="org-active-indicator"></div>
        </button>

        {/* ReliefWeb */}
        <button
          type="button"
          className={`nav-pill-btn org-btn-reliefweb ${activeTab === 'tab-reliefweb' ? 'active' : ''}`}
          onClick={() => setActiveTab('tab-reliefweb')}
          role="tab"
          aria-selected={activeTab === 'tab-reliefweb'}
          title="ReliefWeb - United Nations OCHA Humanitarian Situation Reports"
        >
          <div className="org-logo-frame">
            <svg className="org-logo-svg" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="28" height="28" rx="6" fill="#031a29" stroke="#0284c7" strokeWidth="1.2" />
              <rect x="5.5" y="5.5" width="17" height="17" rx="3.5" fill="#0284c7" />
              <path d="M14 6.8L18.8 11.6L14 16.4L9.2 11.6L14 6.8Z" fill="#ffffff" />
              <path d="M14 11.6L18.8 16.4L14 21.2L9.2 16.4L14 11.6Z" fill="#38bdf8" />
              <circle cx="14" cy="14" r="2.2" fill="#0369a1" />
            </svg>
          </div>
          <div className="org-text-content">
            <div className="org-primary-name">ReliefWeb</div>
            <div className="org-sub-badge">UN OCHA Sitreps</div>
          </div>
          <div className="org-active-indicator"></div>
        </button>

        {/* NASA FIRMS */}
        <button
          type="button"
          className={`nav-pill-btn org-btn-firms ${activeTab === 'tab-firms' ? 'active' : ''}`}
          onClick={() => setActiveTab('tab-firms')}
          role="tab"
          aria-selected={activeTab === 'tab-firms'}
          title="NASA FIRMS - Fire Information for Resource Management System"
        >
          <div className="org-logo-frame">
            <svg className="org-logo-svg" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="28" height="28" rx="6" fill="#080e22" stroke="#0b3d91" strokeWidth="1.2" />
              <circle cx="14" cy="14" r="10.5" fill="#0b3d91" />
              <circle cx="8.5" cy="8.5" r="0.65" fill="#ffffff" />
              <circle cx="19" cy="8.5" r="0.55" fill="#ffffff" />
              <circle cx="7.5" cy="15.5" r="0.5" fill="#ffffff" />
              <circle cx="20.5" cy="17" r="0.6" fill="#ffffff" />
              <path d="M8 17.5L14 8.5L20 17.5L14 13.5L8 17.5Z" fill="#e03c31" />
              <ellipse cx="14" cy="14" rx="10" ry="3.6" transform="rotate(-28 14 14)" stroke="#ffffff" strokeWidth="0.75" fill="none" />
              <text
                x="14"
                y="16.2"
                textAnchor="middle"
                fontFamily="'Inter', sans-serif"
                fontWeight="900"
                fontSize="5.4"
                fill="#ffffff"
                letterSpacing="0.4px"
              >
                NASA
              </text>
              <circle cx="21" cy="21" r="3.2" fill="#ea580c" stroke="#000000" strokeWidth="0.8" />
              <path
                d="M21 19.3C21 19.3 22.2 20.3 22.2 21.1C22.2 21.8 21.6 22.4 21 22.4C20.4 22.4 19.8 21.8 19.8 21.1C19.8 20.3 21 19.3 21 19.3Z"
                fill="#fef08a"
              />
            </svg>
          </div>
          <div className="org-text-content">
            <div className="org-primary-name">NASA FIRMS</div>
            <div className="org-sub-badge">Thermal Satellites</div>
          </div>
          <div className="org-active-indicator"></div>
        </button>
      </nav>

      <div className="feeds-tab-content">
        {activeTab === 'tab-verification' && <VerificationPane incident={incident} />}
        {activeTab === 'tab-usgs' && <USGSPane incident={incident} />}
        {activeTab === 'tab-gdacs' && <GDACSPane incident={incident} />}
        {activeTab === 'tab-reliefweb' && <ReliefWebPane incident={incident} />}
        {activeTab === 'tab-firms' && <FIRMSPane incident={incident} />}
      </div>
    </article>
  );
}
