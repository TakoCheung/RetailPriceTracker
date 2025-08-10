# RetailPriceTracker

A comprehensive retail price tracking service with real-time monitoring, web scraping, and intelligent notifications. Built with modern technologies for scalability and performance.

## 🚀 Features

### Core Functionality
- **Real-time Price Tracking** - Monitor prices across major retailers (Amazon, Walmart, Target, Best Buy)
- **Advanced Product Search** - Full-text search with filtering by category, brand, price range
- **Smart Notifications** - Multi-channel alerts via Email, SMS, and WebSocket
- **Price History Analytics** - Historical price tracking with trend analysis
- **Provider Management** - Configurable web scraping for multiple retailers

### Advanced Capabilities
- **Authentication & Authorization** - JWT-based auth with role-based access control
- **Real-time Updates** - WebSocket connections for live price change notifications
- **Caching System** - Redis-based caching for optimal performance
- **Security Features** - Rate limiting, input sanitization, threat detection
- **Health Monitoring** - Comprehensive system health checks and performance metrics
- **Background Processing** - Async task processing for scraping and notifications

## 🏗 Architecture

### Backend (FastAPI)
- **API Layer**: RESTful APIs with comprehensive validation
- **Service Layer**: Business logic with dependency injection
- **Data Layer**: SQLAlchemy with async support, TimescaleDB for time-series data
- **Task Queue**: Background processing with async tasks
- **Real-time**: WebSocket manager for live updates

### Frontend (Next.js)
- Modern React-based interface
- Server-side rendering for optimal performance
- Real-time updates via WebSocket integration

### Database
- **PostgreSQL** - Primary data store with async support
- **Redis** - Caching and session management
- **TimescaleDB** - Time-series optimization for price history

## 🛠 Technology Stack

**Backend:**
- FastAPI 0.104+ (Python async web framework)
- SQLAlchemy 2.0+ (Async ORM)
- Pydantic V2 (Data validation)
- Redis (Caching & sessions)
- Celery (Background tasks)
- WebSockets (Real-time updates)
- Pytest (Testing framework)

**Frontend:**
- Next.js 14+ (React framework)
- TypeScript (Type safety)
- Tailwind CSS (Styling)

**Infrastructure:**
- Docker & Docker Compose (Containerization)
- PostgreSQL 15+ (Primary database)
- Redis 7+ (Cache & message broker)

## 🚦 Quick Start

### Prerequisites
- Docker and Docker Compose
- Git

### Running with Docker Compose

```bash
git clone https://github.com/TakoCheung/RetailPriceTracker.git
cd RetailPriceTracker
docker-compose up --build
```

**Services will be available at:**
- 🌐 **Frontend**: http://localhost:3000
- 🔧 **Backend API**: http://localhost:8000
- 📊 **API Documentation**: http://localhost:8000/docs
- 🔍 **Health Check**: http://localhost:8000/health

### Docker Commands Reference

#### Basic Operations
```bash
# Start all services
docker-compose up -d

# Start with build (recommended for first run or after changes)
docker-compose up --build

# Start specific services
docker-compose up backend db redis

# Stop all services
docker-compose down

# Stop and remove volumes (⚠️ destroys data)
docker-compose down -v

# View service logs
docker-compose logs backend
docker-compose logs -f frontend  # Follow logs
```

#### Development Workflow
```bash
# Rebuild specific service
docker-compose build backend
docker-compose up -d backend

# Execute commands inside containers
docker-compose exec backend bash
docker-compose exec backend pytest
docker-compose exec db psql -U user -d retailtracker

# View running containers
docker-compose ps

# Monitor resource usage
docker-compose top
```

#### Database Operations
```bash
# Run database migrations
docker-compose exec backend alembic upgrade head

# Access PostgreSQL shell
docker-compose exec db psql -U user -d retailtracker

# Backup database
docker-compose exec db pg_dump -U user retailtracker > backup.sql

# Restore database
docker-compose exec -T db psql -U user -d retailtracker < backup.sql

# Reset database (⚠️ destroys all data)
docker-compose down -v
docker volume rm retailpricetracker_postgres_data
docker-compose up -d db
```

#### Redis Operations
```bash
# Access Redis CLI
docker-compose exec redis redis-cli

# Clear all cached data
docker-compose exec redis redis-cli FLUSHALL

# Monitor Redis commands
docker-compose exec redis redis-cli MONITOR

# Get Redis info
docker-compose exec redis redis-cli INFO
```

### Docker Environment Configuration

#### Development Environment (docker-compose.yml)
- Hot reloading enabled
- Debug mode activated
- Volume mounts for code changes
- Exposed ports for direct access

#### Production Environment (docker-compose.prod.yml)
```bash
# Production deployment
docker-compose -f docker-compose.prod.yml up -d --build

# Scale services
docker-compose -f docker-compose.prod.yml up -d --scale backend=3

# Update production deployment
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --no-deps backend
```

### Development Setup

```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install
npm run dev
```

## 📚 API Documentation

### Core Endpoints

#### Product Management
```http
GET    /api/v2/products                  # List products with filtering
POST   /api/v2/products                  # Create new product
GET    /api/v2/products/{id}             # Get specific product
PUT    /api/v2/products/{id}             # Update product
DELETE /api/v2/products/{id}             # Soft delete product
POST   /api/v2/products/search           # Advanced search
```

#### Provider Management
```http
GET    /api/v2/providers                 # List providers
POST   /api/v2/providers                 # Create provider
POST   /api/v2/providers/{id}/scrape     # Scrape products
POST   /api/v2/providers/{id}/update-prices  # Update all prices
GET    /api/v2/providers/{id}/performance    # Performance metrics
```

#### Price & Analytics
```http
POST   /api/products/{id}/prices         # Add price record
GET    /api/products/{id}/price-history  # Get price history
GET    /api/analytics/trends             # Price trends
GET    /api/analytics/dashboard          # Analytics dashboard
```

#### Notifications & Monitoring
```http
POST   /api/notifications/price-alert    # Send price alert
GET    /api/monitoring/health            # System health
GET    /api/monitoring/performance       # Performance metrics
```

### WebSocket Endpoints
```javascript
// Real-time price updates
const ws = new WebSocket('ws://localhost:8000/ws?token=your_jwt_token');

// Subscribe to product price changes
ws.send(JSON.stringify({
  type: 'subscribe',
  product_id: 123
}));
```

## 🧪 Testing

Comprehensive test suite with 18+ test modules covering:

```bash
# Run all tests
cd backend
pytest

# Run specific test modules
pytest tests/test_product_service.py -v
pytest tests/test_provider_service.py -v
pytest tests/test_websocket_notifications.py -v

# Run with coverage
pytest --cov=app tests/
```

**Test Coverage:**
- Unit Tests (Service layer)
- Integration Tests (API endpoints)
- Performance Tests (Load testing)
- Security Tests (Vulnerability scanning)
- Real-time Tests (WebSocket functionality)

## 🔧 Configuration

### Environment Variables

Create `.env` files in backend/ and frontend/ directories:

**Backend (.env):**
```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/retailtracker
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key-here
ALLOWED_ORIGINS=http://localhost:3000
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
```

**Frontend (.env.local):**
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-nextauth-secret
```

## 🚀 Deployment

### Docker-based Deployment Options

#### 1. Development Deployment
```bash
# Quick start for development
docker-compose up --build

# Run in background
docker-compose up -d --build

# View logs
docker-compose logs -f
```

#### 2. Production Deployment
```bash
# Production build with optimized settings
docker-compose -f docker-compose.prod.yml up --build -d

# Database migrations
docker-compose exec backend alembic upgrade head

# Health check
curl http://localhost:8000/health
```

#### 3. Staging Environment
```bash
# Staging with production-like settings
docker-compose -f docker-compose.staging.yml up -d --build
```

### Container Architecture

```yaml
# Service Overview
services:
  frontend:        # Next.js application
  backend:         # FastAPI application  
  db:             # PostgreSQL database
  redis:          # Redis cache & sessions
  nginx:          # Reverse proxy (production)
  worker:         # Background task processor
```

### Docker Compose Profiles

#### Development Profile
```bash
# Start core services only
docker-compose --profile dev up

# Include monitoring tools
docker-compose --profile dev --profile monitoring up
```

#### Production Profile  
```bash
# Production with all services
docker-compose --profile prod up -d

# With SSL and monitoring
docker-compose --profile prod --profile ssl --profile monitoring up -d
```

### Container Health Monitoring
```bash
# Check container health
docker-compose ps
docker inspect $(docker-compose ps -q backend) --format='{{.State.Health.Status}}'

# Monitor resource usage
docker stats $(docker-compose ps -q)

# Container logs with timestamps
docker-compose logs --timestamps backend
```

### Docker Networking
```bash
# List networks
docker network ls

# Inspect network configuration
docker network inspect retailpricetracker_default

# Test connectivity between containers
docker-compose exec backend ping db
docker-compose exec backend nslookup redis
```

### Volume Management
```bash
# List volumes
docker volume ls

# Backup volumes
docker run --rm -v retailpricetracker_postgres_data:/data \
  -v $(pwd):/backup ubuntu tar czf /backup/postgres_backup.tar.gz -C /data .

# Restore volumes
docker run --rm -v retailpricetracker_postgres_data:/data \
  -v $(pwd):/backup ubuntu tar xzf /backup/postgres_backup.tar.gz -C /data
```

### Scaling Considerations
- **Horizontal Scaling**: Multiple backend instances with load balancer
- **Database**: PostgreSQL clustering or read replicas
- **Caching**: Redis Cluster for high availability
- **Background Tasks**: Multiple Celery workers

## 📊 Monitoring & Observability

### Health Checks
- `/health` - Overall system health
- `/monitoring/status` - Detailed component status
- `/monitoring/performance` - Performance metrics
- `/monitoring/dashboard` - System overview

### Performance Metrics
- Response time monitoring
- Database query performance
- Cache hit rates
- WebSocket connection stats
- Background task processing rates

## 🔐 Security Features

- **Authentication**: JWT tokens with refresh mechanism
- **Authorization**: Role-based access control (Admin, User, Viewer)
- **Rate Limiting**: Per-endpoint and per-user limits
- **Input Validation**: Comprehensive request validation
- **Security Scanning**: SQL injection, XSS, path traversal detection
- **API Security**: CORS, input sanitization, secure headers

## 📈 Performance Optimization

- **Caching Strategy**: Multi-level Redis caching
- **Database Optimization**: Query optimization, indexing
- **Async Processing**: Non-blocking I/O operations
- **Response Compression**: Gzip compression for API responses
- **Connection Pooling**: Efficient database connections

## 🔄 Development Workflow

This project follows **Test-Driven Development (TDD)**:

1. **Red**: Write failing tests first
2. **Green**: Implement minimal code to pass tests  
3. **Refactor**: Optimize code while keeping tests green

### Contributing
1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new functionality
4. Implement the feature
5. Ensure all tests pass (`pytest`)
6. Commit changes (`git commit -m 'Add amazing feature'`)
7. Push to branch (`git push origin feature/amazing-feature`)
8. Open Pull Request

## 🐛 Troubleshooting

### Common Issues

#### Docker & Container Issues

**Container won't start:**
```bash
# Check container status and logs
docker-compose ps
docker-compose logs backend

# Rebuild containers from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

**Port conflicts:**
```bash
# Check what's using ports
lsof -i :8000  # Backend port
lsof -i :3000  # Frontend port
lsof -i :5432  # PostgreSQL port

# Use different ports
docker-compose up -d -p 8001:8000 backend
```

**Out of disk space:**
```bash
# Clean up Docker resources
docker system prune -a
docker volume prune

# Remove unused images
docker image prune -a

# Check disk usage
docker system df
```

**Network connectivity issues:**
```bash
# Check Docker networks
docker network ls
docker network inspect retailpricetracker_default

# Test container connectivity
docker-compose exec backend ping db
docker-compose exec frontend wget -qO- http://backend:8000/health
```

#### Database Connection Issues

**PostgreSQL connection errors:**
```bash
# Check database status
docker-compose logs db

# Verify database is accepting connections
docker-compose exec db pg_isready -U user

# Reset database
docker-compose down -v
docker-compose up -d db
docker-compose exec backend alembic upgrade head
```

**Database permission issues:**
```bash
# Check database users and permissions
docker-compose exec db psql -U user -d retailtracker -c "\du"

# Recreate database with correct permissions
docker-compose exec db createdb -U user retailtracker
```

#### Redis Connection Issues

**Redis connection failures:**
```bash
# Check Redis status
docker-compose logs redis

# Test Redis connectivity
docker-compose exec redis redis-cli ping

# Clear Redis cache
docker-compose exec redis redis-cli FLUSHALL

# Restart Redis
docker-compose restart redis
```

#### Performance Issues

**Slow container startup:**
```bash
# Use cached builds
docker-compose build --build-arg BUILDKIT_INLINE_CACHE=1

# Optimize Docker build context
echo "node_modules\n.git\n*.pyc\n__pycache__" > .dockerignore
```

**High memory usage:**
```bash
# Monitor resource usage
docker stats $(docker-compose ps -q)

# Limit container resources
docker-compose up -d --scale backend=2 --memory="1g" --cpus="1.5"
```

**Slow API responses:**
```bash
# Check backend logs for slow queries
docker-compose logs backend | grep -i "slow"

# Monitor database performance
docker-compose exec db pg_stat_statements
```

#### Development Environment Issues

**Hot reload not working:**
```bash
# Ensure volumes are properly mounted
docker-compose down
docker-compose up -d --force-recreate

# Check file system events
docker-compose exec backend ls -la /app
```

**Environment variables not loaded:**
```bash
# Verify .env file is in correct location
ls -la .env backend/.env frontend/.env.local

# Restart containers after env changes
docker-compose down
docker-compose up -d
```

#### SSL/HTTPS Issues (Production)

**Certificate problems:**
```bash
# Check SSL certificates
docker-compose exec nginx nginx -t

# Renew Let's Encrypt certificates
docker-compose exec certbot certbot renew
```

#### WebSocket Connection Issues
- Ensure JWT token is valid and not expired
- Check CORS settings for WebSocket connections
- Verify WebSocket URL format: `ws://localhost:8000/ws?token=your_jwt`
- Check nginx WebSocket proxy configuration in production

### Debug Mode

**Enable debug logging:**
```bash
# Set debug environment variables
docker-compose -f docker-compose.debug.yml up

# Or export debug flags
export DEBUG=1
export LOG_LEVEL=DEBUG
docker-compose up
```

**Access container shells for debugging:**
```bash
# Backend debugging
docker-compose exec backend bash
docker-compose exec backend python -c "import app; print(app.__version__)"

# Database debugging
docker-compose exec db psql -U user -d retailtracker
docker-compose exec db pg_dump -U user --schema-only retailtracker
```

### Getting Help

If you encounter issues not covered here:

1. **Check logs first**: `docker-compose logs service_name`
2. **Verify service health**: `docker-compose ps`
3. **Check resource usage**: `docker stats`
4. **Review configuration**: Ensure `.env` files are properly configured
5. **Search existing issues**: Check GitHub Issues for similar problems
6. **Create detailed bug report**: Include logs, system info, and reproduction steps

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Support

- **Documentation**: Check `/docs` endpoint for API documentation
- **Issues**: Report bugs via GitHub Issues
- **Community**: Join our discussions for questions and feature requests

---

**Built with ❤️ using modern Python and JavaScript technologies**
