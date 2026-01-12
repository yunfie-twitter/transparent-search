# Build stage
FROM node:18-alpine AS builder

WORKDIR /build

# Copy package files
COPY package.json ./

# Install dependencies
# If package-lock.json exists, use it; otherwise use npm install
COPY package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Copy source code
COPY public ./public
COPY src ./src

# Build React application
RUN npm run build

# Runtime stage
FROM node:18-alpine

WORKDIR /app

# Install only production dependencies for Express server
COPY package.json ./
COPY package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --only=production; else npm install --production; fi

# Copy built React app from builder
COPY --from=builder /build/build ./build

# Copy Express proxy server
COPY server.js ./

# Expose port
EXPOSE 8081

# Set environment variables
ENV NODE_ENV=production
ENV PORT=8081

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD node -e "require('http').get('http://localhost:8081/health', (r) => {if (r.statusCode !== 200) throw new Error(r.statusCode)})" || exit 1

# Start server
CMD ["npm", "start"]
