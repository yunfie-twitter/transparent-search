import React from 'react';
import './LoadingSpinner.css';

function LoadingSpinner() {
  return (
    <div className="loading-container">
      <div className="spinner"></div>
      <p>検索中...</p>
    </div>
  );
}

export default LoadingSpinner;
