import React, { useState, useCallback } from 'react';
import './App.css';
import SearchBox from './components/SearchBox';
import ResultsList from './components/ResultsList';
import Pagination from './components/Pagination';
import LoadingSpinner from './components/LoadingSpinner';
import ErrorMessage from './components/ErrorMessage';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || '/api';

function App() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [limit, setLimit] = useState(10);
  const [totalResults, setTotalResults] = useState(0);
  const [searchMeta, setSearchMeta] = useState(null);

  const performSearch = useCallback(async (searchQuery, page = 1, itemsPerPage = limit) => {
    if (!searchQuery.trim()) {
      setError('検索キーワードを入力してください');
      return;
    }

    setLoading(true);
    setError('');
    setResults([]);
    setCurrentPage(page);
    setLimit(itemsPerPage);

    try {
      const offset = (page - 1) * itemsPerPage;
      const url = `${API_BASE_URL}/search?q=${encodeURIComponent(searchQuery)}&limit=${itemsPerPage}&offset=${offset}`;
      
      console.log(`🚀 Fetching: ${url}`);
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      console.log('✅ Response received:', data);

      if (data.data && Array.isArray(data.data)) {
        setResults(data.data);
        setTotalResults(data.meta.count || 0);
        setSearchMeta(data.meta);
        setQuery(searchQuery);
      } else {
        throw new Error('不正なapiresponse: dataがallusArray');
      }
    } catch (err) {
      console.error('❌ Search error:', err);
      setError(`⚠️ エラー: ${err.message}`);
      setResults([]);
      setTotalResults(0);
    } finally {
      setLoading(false);
    }
  }, [limit]);

  const handleSearch = (searchQuery) => {
    performSearch(searchQuery, 1);
  };

  const handlePageChange = (newPage) => {
    performSearch(query, newPage, limit);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleLimitChange = (newLimit) => {
    performSearch(query, 1, newLimit);
  };

  const totalPages = Math.ceil(totalResults / limit);

  return (
    <div className="App">
      <header className="App-header">
        <div className="header-content">
          <h1 className="logo">🔍 Transparent Search</h1>
          <p className="subtitle">Zero-ETL Search Engine with PostgreSQL & PGroonga</p>
        </div>
      </header>

      <main className="App-main">
        <div className="container">
          <SearchBox onSearch={handleSearch} />

          {loading && <LoadingSpinner />}
          {error && <ErrorMessage message={error} />}

          {results.length > 0 && (
            <>
              <div className="search-controls">
                <div className="control-group">
                  <label htmlFor="limit-select">ページあたり：</label>
                  <select
                    id="limit-select"
                    value={limit}
                    onChange={(e) => handleLimitChange(parseInt(e.target.value))}
                  >
                    <option value="10">10 件</option>
                    <option value="20">20 件</option>
                    <option value="50">50 件</option>
                  </select>
                </div>
              </div>

              <div className="status-bar">
                <span>全 {totalResults} 件 (</span>
                {searchMeta && <span>{searchMeta.took_ms}ms</span>}
                <span>)</span>
              </div>

              <ResultsList
                results={results}
                offset={(currentPage - 1) * limit}
              />

              {totalPages > 1 && (
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  onPageChange={handlePageChange}
                />
              )}
            </>
          )}
        </div>
      </main>

      <footer className="App-footer">
        <p>💚 Powered by Transparent Search | ✨ Frontend &amp; Backend Separated</p>
      </footer>
    </div>
  );
}

export default App;
