import React from 'react';

export default function JsonModal({ isOpen, onClose, incident }) {
  if (!isOpen) return null;

  const jsonStr = incident ? JSON.stringify(incident, null, 2) : '{}';

  return (
    <div
      className="modal-overlay open"
      id="json-modal"
      onClick={(e) => {
        if (e.target.id === 'json-modal') onClose();
      }}
    >
      <div className="modal-box">
        <div className="modal-header">
          <span className="modal-title">Unified Incident Report JSON</span>
          <button
            type="button"
            className="modal-close-btn"
            id="btn-close-json-modal"
            onClick={onClose}
          >
            &times;
          </button>
        </div>
        <div className="modal-body">
          <pre className="code-view" id="json-code-display">
            {jsonStr}
          </pre>
        </div>
      </div>
    </div>
  );
}
