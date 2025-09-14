-- Tabla para usuarios registrados para mensajes directos
CREATE TABLE direct_message_users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Habilitar RLS
ALTER TABLE direct_message_users ENABLE ROW LEVEL SECURITY;

-- Política para permitir todas las operaciones (para el bot)
CREATE POLICY "Allow all operations" ON direct_message_users FOR ALL USING (true);
