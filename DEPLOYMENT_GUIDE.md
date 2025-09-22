# 🚀 GUÍA DE DEPLOYMENT GRATUITO

## Arquitectura de Deployment

```
Frontend (Next.js) → Vercel (Gratis)
Backend (FastAPI) → Railway (Gratis)
Database (PostgreSQL) → Supabase (Gratis)
CI/CD → GitHub Actions (Gratis)
```

## 📋 CONFIGURACIÓN PASO A PASO

### 1. 🗄️ BASE DE DATOS (Supabase)

#### Crear Cuenta en Supabase
1. Ve a [supabase.com](https://supabase.com)
2. Registrarte con GitHub
3. Crear nuevo proyecto: "trading-simulator"
4. Esperar a que se inicialice (2-3 minutos)

#### Configurar Database
1. En el dashboard de Supabase, ir a "SQL Editor"
2. Ejecutar el script completo de `database/schema.sql`
3. Copiar la connection string desde "Settings" → "Database"
4. Format: `postgresql+asyncpg://postgres:[password]@[host]:5432/postgres`

#### Variables de Entorno
```bash
SUPABASE_DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@HOST:5432/postgres
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key
```

### 2. 🖥️ BACKEND (Railway)

#### Crear Cuenta en Railway
1. Ve a [railway.app](https://railway.app)
2. Registrarte con GitHub
3. Conectar tu repositorio

#### Deploy Backend
1. En Railway dashboard: "New Project"
2. "Deploy from GitHub repo"
3. Seleccionar tu repositorio
4. Railway detectará automáticamente el Dockerfile
5. Configurar variables de entorno:

```bash
# Database
SUPABASE_DATABASE_URL=tu_supabase_url

# APIs
ALPHA_VANTAGE_API_KEY=tu_alpha_vantage_key
NEWS_API_KEY=tu_news_api_key

# Environment
ENVIRONMENT=production
PORT=8000
PYTHONPATH=/app
```

#### Configurar Domain
1. En Railway dashboard → "Settings" → "Domains"
2. "Generate Domain" → `https://tu-app.railway.app`
3. Copiar URL para el frontend

#### Custom Domain (Opcional)
```bash
# Si tienes dominio propio
RAILWAY_DOMAIN=api.tudominio.com
```

### 3. 🌐 FRONTEND (Vercel)

#### Crear Cuenta en Vercel
1. Ve a [vercel.com](https://vercel.com)
2. Registrarte con GitHub
3. Importar proyecto

#### Deploy Frontend
1. En Vercel dashboard: "Add New" → "Project"
2. Importar tu repositorio de GitHub
3. Framework Preset: "Next.js"
4. Root Directory: `frontend`
5. Configurar variables de entorno:

```bash
NEXT_PUBLIC_API_URL=https://tu-backend.railway.app
NEXT_PUBLIC_APP_NAME=Trading Simulator
NEXT_PUBLIC_APP_VERSION=1.0.0
```

#### Configurar Build
```bash
# Build Command
npm run build

# Output Directory
.next

# Install Command
npm install
```

### 4. 🔄 CI/CD (GitHub Actions)

#### Configurar Secrets en GitHub
1. Ve a tu repositorio → "Settings" → "Secrets and variables" → "Actions"
2. Añadir estos secrets:

```bash
# Railway
RAILWAY_TOKEN=tu_railway_token

# Vercel
VERCEL_TOKEN=tu_vercel_token
VERCEL_ORG_ID=tu_org_id
VERCEL_PROJECT_ID=tu_project_id

# Database
SUPABASE_DATABASE_URL=tu_supabase_url

# APIs
ALPHA_VANTAGE_API_KEY=tu_alpha_vantage_key
NEWS_API_KEY=tu_news_api_key

# Backend URL (for migrations)
BACKEND_URL=https://tu-backend.railway.app
ADMIN_TOKEN=optional_admin_token
```

#### Obtener Tokens

**Railway Token:**
1. Railway dashboard → "Account Settings" → "Tokens"
2. "Create New Token"

**Vercel Token:**
1. Vercel dashboard → "Settings" → "Tokens"
2. "Create New Token"

**Vercel IDs:**
```bash
# Desde Vercel CLI
npm i -g vercel
vercel
# Te dará los IDs después del primer deploy
```

### 5. 📊 MONITOREO Y LOGS

#### Railway Logs
```bash
# Ver logs en Railway dashboard
Deployments → Click en deployment → View Logs
```

#### Vercel Logs
```bash
# Ver logs en Vercel dashboard
Functions → View Function Logs
```

#### Supabase Logs
```bash
# Ver logs en Supabase dashboard
Logs → API Logs
```

## 🔧 CONFIGURACIÓN AVANZADA

### Custom Domains
```bash
# Frontend (Vercel)
tudominio.com → Vercel

# Backend (Railway)
api.tudominio.com → Railway
```

### Environment Variables por Staging

#### Development
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
DATABASE_URL=postgresql://localhost:5432/trading_simulator_dev
```

#### Staging
```bash
NEXT_PUBLIC_API_URL=https://staging-api.railway.app
DATABASE_URL=postgresql://staging-supabase-url
```

#### Production
```bash
NEXT_PUBLIC_API_URL=https://api.railway.app
DATABASE_URL=postgresql://production-supabase-url
```

### Scaling Configuration

#### Railway
```bash
# En railway.toml
[build]
builder = "DOCKERFILE"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3

[variables]
PORT = "8000"
```

#### Vercel
```json
// En vercel.json
{
  "functions": {
    "app/api/**/*.ts": {
      "maxDuration": 30
    }
  },
  "regions": ["iad1"],
  "framework": "nextjs"
}
```

## 🚀 DEPLOYMENT AUTOMÁTICO

### Push to Deploy
```bash
git add .
git commit -m "feat: add new trading feature"
git push origin main

# GitHub Actions automáticamente:
# 1. Ejecuta tests
# 2. Deploya backend a Railway
# 3. Deploya frontend a Vercel
# 4. Ejecuta migraciones de DB
```

### Manual Deploy
```bash
# Railway CLI
railway login
railway deploy

# Vercel CLI
vercel --prod
```

## 📊 COSTOS (TODO GRATIS)

### Límites Free Tier

**Supabase (Database):**
- 2 proyectos gratis
- 500MB database
- 1GB file storage
- 5GB bandwidth/mes

**Railway (Backend):**
- $5 crédito mensual gratis
- Suficiente para apps pequeñas-medianas
- Pay-per-use después

**Vercel (Frontend):**
- 100GB bandwidth
- 6,000 build minutes
- Unlimited static hosting

**GitHub Actions:**
- 2,000 build minutes/mes gratis

### Optimizaciones para Free Tier
```bash
# Reducir builds en Railway
- Solo hacer build en main branch
- Usar cache de Docker layers

# Optimizar Vercel
- Usar Static Generation donde sea posible
- Optimizar imágenes
- Minimizar API calls

# Optimizar Supabase
- Usar indexes apropiados
- Limpiar datos old regularmente
- Usar RLS (Row Level Security)
```

## 🔒 SEGURIDAD

### Environment Variables
```bash
# NUNCA commitear en git
.env
.env.local
.env.production

# Usar secretos en platforms
Railway → Environment Variables
Vercel → Environment Variables
GitHub → Secrets
```

### Database Security
```bash
# Supabase RLS
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can only see own portfolios" ON portfolios
FOR ALL USING (user_id = auth.uid());
```

### API Security
```bash
# Rate limiting en FastAPI
from slowapi import Limiter

@app.get("/api/data")
@limiter.limit("100/minute")
async def get_data():
    pass
```

## 🎯 NEXT STEPS

1. **Setup inicial**: Seguir pasos 1-4
2. **Test deployment**: Hacer push a main
3. **Monitor logs**: Verificar que todo funcione
4. **Custom domain**: Configurar dominio propio
5. **Optimizations**: Implementar caching, CDN
6. **Monitoring**: Añadir Sentry, analytics
7. **Scaling**: Upgrade plans según necesidad

## 🆘 TROUBLESHOOTING

### Common Issues

**Railway Build Fails:**
```bash
# Check Dockerfile
# Verify dependencies in requirements.txt
# Check logs in Railway dashboard
```

**Vercel Build Fails:**
```bash
# Check package.json
# Verify Node.js version
# Check build logs in Vercel dashboard
```

**Database Connection Issues:**
```bash
# Verify Supabase URL format
# Check firewall/security groups
# Test connection with psql
```

**CORS Issues:**
```bash
# Add frontend domain to CORS_ORIGINS in FastAPI
# Check Vercel domain in Railway env vars
```

¡Con esta configuración tendrás un sistema completo de trading simulator deployado gratuitamente! 🚀