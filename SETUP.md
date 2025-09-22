# 🚀 Trading Simulator - Guía de Instalación

## 📋 Configuración del Ambiente Virtual

Para usar el Trading Simulator, necesitas configurar un ambiente virtual de Python:

### 1. Crear Ambiente Virtual
```bash
cd trading_simulator
python3 -m venv trading_env
```

### 2. Activar Ambiente Virtual
```bash
source trading_env/bin/activate
```

### 3. Instalar Dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar API Keys
```bash
python main.py --setup
```
Luego edita el archivo `.env` con tus API keys gratuitas.

### 5. Verificar Instalación
```bash
python test_system.py
```

### 6. Ejecutar el Sistema
```bash
# Ejecutar dashboard
python main.py --dashboard

# Ver portfolio
python main.py --portfolio

# Ver recomendaciones
python main.py --recommendations
```

## 🔑 API Keys Gratuitas

### Alpha Vantage (Datos de Mercado)
1. Ve a: https://www.alphavantage.co/support/#api-key
2. Registrate gratis
3. Obtienes 500 requests/día

### NewsAPI (Noticias)
1. Ve a: https://newsapi.org/register
2. Registrate gratis
3. Obtienes 1000 requests/día

## 🎯 Ejemplo de Configuración Completa

```bash
# 1. Navegar al directorio
cd trading_simulator

# 2. Crear ambiente virtual
python3 -m venv trading_env

# 3. Activar ambiente
source trading_env/bin/activate

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Setup inicial
python main.py --setup

# 6. Editar .env con tus API keys
nano .env

# 7. Verificar instalación
python test_system.py

# 8. Ejecutar dashboard
python main.py --dashboard
```

## 🔧 Solución de Problemas

### Error: "No module named 'xyz'"
```bash
# Asegúrate de tener el ambiente virtual activado
source trading_env/bin/activate
pip install -r requirements.txt
```

### Error: "API Key Demo"
- Asegúrate de haber editado el archivo `.env` con tus API keys reales
- Las API keys "demo" tienen limitaciones

### Error: "No market data"
- Verifica tu conexión a internet
- Puede ser que el mercado esté cerrado
- Revisa que tus API keys sean válidas

### Dashboard no carga
```bash
# Verifica que el puerto 8050 esté libre
python main.py --dashboard
# Luego abre: http://127.0.0.1:8050
```

## 🎉 ¡Listo!

Una vez configurado, el sistema:
- ✅ Recolecta datos de mercado automáticamente
- ✅ Analiza noticias con IA
- ✅ Genera señales de trading
- ✅ Proporciona recomendaciones diarias
- ✅ Trackea performance
- ✅ Ejecuta simulación continua

## 💡 Comandos Útiles

```bash
# Ver estado del portfolio
python main.py --portfolio

# Ver recomendaciones del día
python main.py --recommendations

# Ver señales actuales
python main.py --signals

# Actualización manual
python main.py --update

# Solo dashboard
python main.py --dashboard

# Sistema completo automático
python main.py --scheduler
```

## 📊 Próximos Pasos

1. Monitorea el dashboard diariamente
2. Revisa las recomendaciones
3. Ejecuta trades manualmente en tu broker
4. Compara performance con el simulador
5. Ajusta estrategias según resultados

¡Happy Trading! 📈💰