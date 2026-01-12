/**
 * Express.js Proxy Server
 * Serves React frontend on port 8081 and proxies API requests to backend (port 8080)
 */

const express = require('express');
const path = require('path');
const { createProxyMiddleware } = require('http-proxy-middleware');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 8081;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8080';

console.log(`🚀 Frontend Server Configuration:`);
console.log(`   Frontend Port: ${PORT}`);
console.log(`   Backend URL: ${BACKEND_URL}`);
console.log(`   React Build Dir: ${path.join(__dirname, 'build')}`);

// ==================== MIDDLEWARE ====================

// Enable CORS for local development
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, PATCH, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(200);
  }
  next();
});

// ==================== PROXY CONFIGURATION ====================

// Proxy /api/* to backend
app.use(
  '/api',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    pathRewrite: {
      '^/api': '/api',  // Keep /api prefix
    },
    onError: (err, req, res) => {
      console.error(`❌ Proxy error: ${err.message}`);
      res.status(503).json({
        error: 'Backend service unavailable',
        message: err.message,
      });
    },
    onProxyRes: (proxyRes) => {
      console.log(`✅ [${proxyRes.statusCode}] ${proxyRes.req.method} ${proxyRes.req.path}`);
    },
  })
);

// Proxy /health to backend
app.use(
  '/health',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
  })
);

// Proxy /admin to backend
app.use(
  '/admin',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
  })
);

// ==================== STATIC FILES & REACT ====================

// Serve React build files
const buildDir = path.join(__dirname, 'build');
app.use(express.static(buildDir, {
  maxAge: '1d',
  etag: false,
}));

// SPA catch-all: Route all unmatched requests to React's index.html
app.get('*', (req, res) => {
  res.sendFile(path.join(buildDir, 'index.html'));
});

// ==================== ERROR HANDLING ====================

app.use((err, req, res, next) => {
  console.error(`❌ Server error: ${err.message}`);
  res.status(500).json({
    error: 'Internal server error',
    message: err.message,
  });
});

// ==================== START SERVER ====================

app.listen(PORT, '0.0.0.0', () => {
  console.log(`\n✅ Frontend server running on http://0.0.0.0:${PORT}`);
  console.log(`✅ Backend proxy configured: ${BACKEND_URL}`);
  console.log(`\n📍 Navigation:`);
  console.log(`   Frontend: http://localhost:${PORT}`);
  console.log(`   API Docs: http://localhost:${PORT}/api/docs`);
  console.log(`   Health Check: http://localhost:${PORT}/health`);
  console.log(`\n⚡ Ready to accept requests\n`);
});

process.on('SIGTERM', () => {
  console.log('\n🛑 SIGTERM received, shutting down gracefully...');
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('\n🛑 SIGINT received, shutting down gracefully...');
  process.exit(0);
});
