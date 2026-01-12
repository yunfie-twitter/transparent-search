import React from 'react';
import './ErrorMessage.css';

function ErrorMessage({ message }) {
  return (
    <div className="error-container">
      <p className="error-message">{message}</p>
    </div>
  );
}

export default ErrorMessage;
