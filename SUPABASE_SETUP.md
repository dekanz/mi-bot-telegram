# 🗄️ CONFIGURACIÓN DE SUPABASE

## 📋 Pasos para configurar la base de datos en la nube

### 1. Crear cuenta en Supabase
1. Ve a [https://supabase.com](https://supabase.com)
2. Crea una cuenta gratuita
3. Crea un nuevo proyecto

### 2. Obtener credenciales
1. En tu proyecto de Supabase, ve a **Settings** → **API**
2. Copia la **URL** del proyecto
3. Copia la **anon public** key

### 3. Configurar variables de entorno en Render
1. Ve a tu proyecto en Render
2. Ve a **Environment**
3. Agrega estas variables:
   - `SUPABASE_URL`: https://tu-proyecto.supabase.co
   - `SUPABASE_KEY`: tu-clave-publica-anonima

### 4. Crear tablas en Supabase
Ejecuta este SQL en el **SQL Editor** de Supabase:

```sql
-- Tabla de usuarios registrados
CREATE TABLE registered_users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabla de logs
CREATE TABLE user_registration_log (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    action TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    details TEXT
);
```

### 5. Configurar políticas de seguridad (RLS)
```sql
-- Habilitar RLS
ALTER TABLE registered_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_registration_log ENABLE ROW LEVEL SECURITY;

-- Política para permitir todas las operaciones (para el bot)
CREATE POLICY "Allow all operations" ON registered_users FOR ALL USING (true);
CREATE POLICY "Allow all operations" ON user_registration_log FOR ALL USING (true);
```

## ✅ Ventajas de Supabase
- ✅ **Base de datos PostgreSQL** en la nube
- ✅ **Respaldo automático** diario
- ✅ **Escalabilidad** automática
- ✅ **API REST** integrada
- ✅ **Gratis** hasta 500MB
- ✅ **Persistencia** garantizada

## 🔧 Comandos del bot
- `/register` - Registrarse
- `/unregister` - Desregistrarse
- `/registered` - Ver usuarios registrados
- `/historial` - Ver historial de acciones
- `/backup` - Confirmar respaldo automático
- `/count` - Estadísticas del grupo
