import React, { useState } from 'react';
import './SearchBox.css';

function SearchBox({ onSearch }) {
  const [input, setInput] = useState('');
  const [isFocused, setIsFocused] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim()) {
      onSearch(input);
    }
  };

  const handleChange = (e) => {
    setInput(e.target.value);
  };

  return (
    <div className="search-container">
      <form onSubmit={handleSubmit} className="search-form">
        <div className={`search-box ${isFocused ? 'focused' : ''}`}>
          <input
            type="text"
            className="search-input"
            placeholder="検索キーワードを入力してください..."
            value={input}
            onChange={handleChange}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
          />
          <button type="submit" className="search-button" title="検索">
            🔍
          </button>
        </div>
      </form>
      <p className="search-hint">部分一致検索に対応しています</p>
    </div>
  );
}

export default SearchBox;
