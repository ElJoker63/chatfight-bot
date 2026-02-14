# 🤖 ChatFight Auto-Responder Bot

Bot de Telegram que detecta automáticamente los juegos del bot **ChatFight** y responde automáticamente utilizando inteligencia artificial de **Groq** para analizar las imágenes.

## ✨ Características

- **Auto-Responder Automático**: Detecta cuando el bot ChatFight publica un juego (palabras u operaciones matemáticas) y responde automáticamente
- **Análisis de Imágenes con IA**: Utiliza Groq Vision API para analizar las imágenes y encontrar la respuesta correcta
- **Persistencia en MongoDB**: Guarda el estado y estadísticas en MongoDB
- **Comandos de Control**: Comandos para ver estado y activar/desactivar el bot

## 📋 Requisitos

- Python 3.10+
- Cuenta de Telegram
- API ID y Hash de Telegram (obtener en [my.telegram.org](https://my.telegram.org/apps))
- API Key de Groq (gratuita en [console.groq.com](https://console.groq.com/))
- MongoDB (puede ser MongoDB Atlas gratuito o local)

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/ElJoker63/chatfight-bot.git
cd chatfight-bot
```

### 2. Crear entorno virtual (recomendado)

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
copy .env.example .env
```

Edita el archivo `.env` con tus valores:

```env
# Telegram API (obtener en https://my.telegram.org/apps)
API_ID=12345678
API_HASH=tu_api_hash_aqui

# Session String (opcional - ver más abajo)
SESSION_STRING=

# ChatFight IDs
CHATFIGHT_BOT_ID=691070694
CHATFIGHT_GROUP_ID=-100

# MongoDB
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/

# Groq API (gratis en https://console.groq.com/)
GROQ_API_KEY=tu_groq_api_key_aqui
```

### 5. Obtener Session String (primera vez)

Si no tienes un `SESSION_STRING`, el bot te pedirá tu número de teléfono y código de verificación la primera vez que lo ejecutes:

```bash
python main.py
```

El bot guardará la sesión y la próxima vez podrá iniciar sin autenticación manual.

## 🎮 Comandos

| Comando | Descripción |
|---------|-------------|
| `-cf` | Ver estado y estadísticas del bot |
| `-cft` | Activar/Desactivar el auto-responder |
| `-ping` | Verificar que el bot está online |
| `.help` | Mostrar ayuda de comandos |

## 🔧 Configuración Avanzada

### CHATFIGHT_BOT_ID
El ID del bot ChatFight. Por defecto es `691070694`, que es el bot oficial de ChatFight.

### CHATFIGHT_GROUP_ID
El ID del grupo donde está el bot ChatFight. Cambia este valor si usas un grupo diferente.

## 📊 Estadísticas

El bot guarda las siguientes estadísticas en MongoDB:
- Total de respuestas enviadas
- Palabras encontradas
- Operaciones calculadas
- Errores
- Historial de últimas 100 respuestas

## 🐳 Docker (Opcional)

Si prefieres usar Docker:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

```bash
docker build -t chatfight-bot .
docker run -d --env-file .env chatfight-bot
```

## 📝 Notas

- El bot debe ser administrador o tener permisos en el grupo para responder mensajes
- El primer análisis de imagen puede tardar unos segundos
- Groq tiene límites gratuitos generousos pero puedes configurarlos en su dashboard
- Las estadísticas se guardan automáticamente en MongoDB

## 📄 Licencia

MIT License - Puedes usar este código freely.

## 🙏 Agradecimientos

- [Pyrogram](https://docs.pyrogram.org/) - Telegram Bot Framework
- [Groq](https://groq.com/) - AI Inference Platform
- [MongoDB](https://www.mongodb.com/) - Database
