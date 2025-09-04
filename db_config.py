import psycopg2

def conectar_db():
    return psycopg2.connect(
        host = "localhost",
        dbname = "maquinas",
        user = "admaquinas",
        password = "maquinasDB",
        port = "5432"
    )