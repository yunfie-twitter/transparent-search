import React from 'react';
import './ResultsList.css';

function ResultsList({ results, offset }) {
  return (
    <div className="results-list">
      {results.map((result, index) => (
        <div key={result.id || index} className="result-item">
          <div className="result-number">#{offset + index + 1}</div>
          <div className="result-content">
            <a href={result.url} target="_blank" rel="noopener noreferrer" className="result-title">
              {result.title}
            </a>
            <p className="result-url">{result.url}</p>
            <p className="result-snippet">{result.snippet || result.description || 'No description available'}</p>
            <div className="result-meta">
              <span className="result-score">🎯 Score: {(result.relevance_score || 0).toFixed(2)}</span>
              {result.domain && <span className="result-domain">{result.domain}</span>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default ResultsList;
