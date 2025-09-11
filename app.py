# app.py

from datetime import date
import os

import pandas as pd
from psycopg2.extras import execute_values

from datetime import date, datetime
from decimal import Decimal



from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)
import psycopg2
import psycopg2.extras
import bcrypt

# Importa aquí tu función para conectar a la BD (debe devolver psycopg2 connection)
from db_config import conectar_db

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "clave_super_segura")


# -----------------------------
# Utilidades de base de datos
# -----------------------------
def query_uno(sql: str, params: tuple = None):
    conn = conectar_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()
    finally:
        conn.close()


def query_todos(sql: str, params: tuple = None):
    conn = conectar_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def query_valor(sql: str, params: tuple = None):
    conn = conectar_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            fila = cur.fetchone()
            return fila[0] if fila else None
    finally:
        conn.close()


def exec_sql(sql: str, params: tuple = None) -> bool:
    conn = conectar_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
        return True
    except Exception as e:
        # En producción loggear
        print("DB error:", e)
        return False
    finally:
        conn.close()

def exec_sql_returning(sql: str, params: tuple = None):
    """
    Ejecuta SQL y retorna (ok, value) donde value es la primera columna del RETURNING si existe.
    """
    conn = conectar_db()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                value = None
                try:
                    row = cur.fetchone()
                    if row:
                        value = row[0]
                except Exception:
                    value = None
        return True, value
    except Exception as e:
        print("DB error:", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return False, None
    finally:
        conn.close()
      


# -----------------------------
# Autenticación y helpers
# -----------------------------
def verificar_usuario(usuario: str, password: str):
    try:
        row = query_uno(
            "SELECT id_usuario, pass_usuario, rol FROM usuarios WHERE name_usuario = %s LIMIT 1",
            (usuario,),
        )
    except Exception:
        return None

    if not row:
        return None

    id_usuario = row.get("id_usuario")
    hash_password = row.get("pass_usuario")
    rol = row.get("rol")

    if hash_password and bcrypt.checkpw(password.encode("utf-8"), hash_password.encode("utf-8")):
        return {"id_usuario": id_usuario, "name_usuario": usuario, "rol": rol}
    return None


def is_logged_in():
    return session.get("usuario") is not None


def is_admin():
    # Nota: los roles en tu BD son 'Admin' y 'Administrador' (según mencionaste).
    # Aquí consideramos que el rol con permiso total es 'Admin'.
    return session.get("rol") == "Admin"

MESES_NOMBRE = [
    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
]

def normaliza_mes_nombre(mes_str: str) -> str | None:
    """Devuelve el nombre correcto de mes si coincide (ignora mayúsculas/minúsculas/espacios)."""
    if not mes_str:
        return None
    m = mes_str.strip().lower()
    for nombre in MESES_NOMBRE:
        if nombre.lower() == m:
            return nombre  # normalizado, con mayúscula inicial
    return None

def parse_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def parse_date(v):
    # Espera 'YYYY-MM-DD' desde el input type="date"
    try:
        from datetime import datetime
        return datetime.strptime(v, '%Y-%m-%d').date()
    except Exception:
        return None
    
from decimal import Decimal

def _to_float(x):
    """
    Convierte a float desde Decimal/str/None de forma segura.
    Acepta strings con comas de miles.
    """
    if x is None:
        return None
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    # Intentar parsear str
    try:
        s = str(x).strip().replace(",", "")
        return float(s) if s else None
    except Exception:
        return None

def _safe_div(a, b):
    """
    Divide con conversión previa y evita división por cero.
    """
    af = _to_float(a)
    bf = _to_float(b)
    if af is None or bf is None or bf == 0.0:
        return 0.0
    return af / bf



# -----------------------------
# Rutas de autenticación
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        usuario_valido = verificar_usuario(usuario, password)

        if usuario_valido:
            session["usuario"] = usuario_valido["name_usuario"]
            session["rol"] = usuario_valido["rol"]
            return redirect(url_for("inicio"))
        else:
            flash("Usuario o contraseña incorrecta, inténtelo nuevamente...")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------------
# Página principal (panel)
# -----------------------------
@app.route('/')
@app.route('/inicio')
def inicio():
    if not is_logged_in():
        return redirect(url_for("login"))

    fecha_actual = date.today()
    meses = [
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    ]
    anio = fecha_actual.year
    mes_num = fecha_actual.month
    mes = meses[mes_num - 1]

    tipo_cambio_actual = (
        query_uno(
            "SELECT anio, mes, valor_cambio FROM tipo_cambio WHERE anio = %s AND mes = %s LIMIT 1",
            (anio, mes),
        )
        or {"anio": anio, "mes": mes, "valor_cambio": "-"}
    )

    maquinas_activas = query_valor(
        "SELECT COUNT(*) FROM maquinas m JOIN estado e ON e.id_estado = m.id_estado WHERE e.estado = 'Activo'"
    ) or 0

    stacks = query_uno(
        "SELECT SUM(CASE WHEN s.name_stacker = 'UBA' THEN 1 ELSE 0 END) AS uba, SUM(CASE WHEN s.name_stacker = 'Ivizion' THEN 1 ELSE 0 END) AS ivizion, SUM(CASE WHEN s.name_stacker = 'MEI' THEN 1 ELSE 0 END) AS mei FROM maquinas m JOIN tipo_stacker s ON s.id_stacker = m.id_stacker"
    ) or {"uba": 0, "ivizion": 0, "mei": 0}

    progs = query_uno(
        "SELECT SUM(CASE WHEN p.name_jackpot = 'Progresivo' THEN 1 ELSE 0 END) AS progresivo, SUM(CASE WHEN p.name_jackpot = 'Maxi Jackpot' THEN 1 ELSE 0 END) AS maxi_jackpot FROM maquinas m JOIN tipo_jackpots p ON p.id_tipo = m.id_tipo"
    ) or {"progresivo": 0, "maxi_jackpot": 0}

    wigos = query_uno(
        "SELECT SUM(CASE WHEN kw.name_kit = '5.5' THEN 1 ELSE 0 END) AS wigos_55, SUM(CASE WHEN kw.name_kit = '6.4' THEN 1 ELSE 0 END) AS wigos_64 FROM maquinas m JOIN kit_wigos kw ON kw.id_kit = m.id_kit"
    ) or {"wigos_55": 0, "wigos_64": 0}

    maquinas = query_todos(
        "SELECT m.numero, mo.name_modelo, pr.name_proveedor, e.estado, ts.name_stacker, p.name_progresivo, m.piso, m.serie FROM maquinas m LEFT JOIN modelos mo ON mo.id_modelo = m.id_modelo LEFT JOIN proveedores pr ON pr.id_proveedor = mo.id_proveedor LEFT JOIN estado e ON e.id_estado = m.id_estado LEFT JOIN tipo_stacker ts ON ts.id_stacker = m.id_stacker LEFT JOIN progresivos p ON p.id_progresivo = m.id_progresivo WHERE e.estado = 'Activo' ORDER BY m.numero LIMIT 1000"
    )
    maquinas_count = query_valor("SELECT COUNT(*) FROM maquinas") or 0

    proveedores_modelos = query_todos(
        "SELECT pr.name_proveedor, mo.name_modelo FROM modelos mo JOIN proveedores pr ON pr.id_proveedor = mo.id_proveedor ORDER BY pr.name_proveedor, mo.name_modelo LIMIT 2000"
    )
    proveedores_modelos_count = query_valor("SELECT COUNT(*) FROM modelos") or 0

    tipo_cambio = query_todos("SELECT anio, mes, valor_cambio FROM tipo_cambio ORDER BY id_cambio DESC LIMIT 1000")
    tipo_cambio_count = query_valor("SELECT COUNT(*) FROM tipo_cambio") or 0

    return render_template(
        "inicio.html",
        usuario=session["usuario"],
        rol=session["rol"],
        fecha_actual=fecha_actual,
        tipo_cambio_actual=tipo_cambio_actual,
        maquinas_activas=maquinas_activas,
        maquinas_stacker_uba=stacks.get("uba", 0),
        maquinas_stacker_ivizion=stacks.get("ivizion", 0),
        maquinas_stacker_mei=stacks.get("mei", 0),
        maquinas_prog_progresivo=progs.get("progresivo", 0),
        maquinas_prog_maxi=progs.get("maxi_jackpot", 0),
        mes_num=mes_num,
        mes=mes,
        wigos_55=wigos.get("wigos_55", 0),
        wigos_64=wigos.get("wigos_64", 0),
        maquinas=maquinas,
        maquinas_count=maquinas_count,
        proveedores_modelos=proveedores_modelos,
        proveedores_modelos_count=proveedores_modelos_count,
        tipo_cambio=tipo_cambio,
        tipo_cambio_count=tipo_cambio_count,
    )


# -----------------------------
# Sección: Máquinas (vistas y API)
# -----------------------------
@app.route("/maquinas")
def maquinas():
    if not is_logged_in():
        return redirect(url_for("login"))

    filtro_estado = request.args.get("estado")  # "Activo" / "Inactivo" / None
    where_clause = ""
    params = ()
    if filtro_estado:
        where_clause = "WHERE e.estado = %s"
        params = (filtro_estado,)

    sql = f"""
      SELECT
        m.id_maquina, m.numero, m.piso, m.serie,
        e.estado,
        mo.id_modelo, mo.name_modelo,
        pr.name_proveedor,
        tj.name_jackpot,
        ts.name_stacker,
        kw.name_kit,
        pg.name_progresivo
      FROM maquinas m
      LEFT JOIN estado e        ON e.id_estado = m.id_estado
      LEFT JOIN modelos mo      ON mo.id_modelo = m.id_modelo
      LEFT JOIN proveedores pr  ON pr.id_proveedor = mo.id_proveedor
      LEFT JOIN tipo_jackpots tj ON tj.id_tipo = m.id_tipo
      LEFT JOIN tipo_stacker ts ON ts.id_stacker = m.id_stacker
      LEFT JOIN kit_wigos kw    ON kw.id_kit = m.id_kit
      LEFT JOIN progresivos pg  ON pg.id_progresivo = m.id_progresivo
      {where_clause}
      ORDER BY m.numero
    """

    modelos = query_todos("SELECT id_modelo, name_modelo FROM modelos ORDER BY name_modelo")
    estados = query_todos("SELECT id_estado, estado FROM estado ORDER BY estado")
    tipo_jackpots = query_todos("SELECT id_tipo, name_jackpot FROM tipo_jackpots ORDER BY id_tipo")
    tipo_stacker = query_todos("SELECT id_stacker, name_stacker FROM tipo_stacker ORDER BY id_stacker")
    kit_wigos = query_todos("SELECT id_kit, name_kit FROM kit_wigos ORDER BY id_kit")
    progresivos = query_todos("SELECT id_progresivo, name_progresivo FROM progresivos ORDER BY name_progresivo")

    maquinas_list = query_todos(sql, params)
    maquinas_count = query_valor("SELECT COUNT(*) FROM maquinas") or 0
    maquinas_activas = query_valor("SELECT COUNT(*) FROM maquinas WHERE id_estado = 1") or 0

    return render_template(
        "maquinas.html",
        usuario=session["usuario"],
        rol=session["rol"],
        maquinas=maquinas_list,
        maquinas_count=maquinas_count,
        filtro_estado=filtro_estado or "",
        modelos=modelos,
        estados=estados,
        tipo_jackpots=tipo_jackpots,
        tipo_stacker=tipo_stacker,
        kit_wigos=kit_wigos,
        progresivos=progresivos,
        maquinas_activas=maquinas_activas,
    )


@app.route("/api/maquinas/<int:id>")
def api_maquina_detalle(id: int):
    d = query_uno(
        "SELECT id_maquina, id_modelo, numero, id_estado, id_tipo, id_stacker, id_kit, piso, id_progresivo, serie FROM maquinas WHERE id_maquina = %s LIMIT 1",
        (id,),
    )
    return jsonify(d or {})


@app.route("/api/maquinas", methods=["POST"])
def api_maquina_crear():
    if not is_admin():
        return jsonify(ok=False, msg="No autorizado"), 403

    data = request.get_json() or {}
    try:
        ok = exec_sql(
            "INSERT INTO maquinas (id_modelo, numero, id_estado, id_tipo, id_stacker, id_kit, piso, id_progresivo, serie) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                data.get("id_modelo") or None,
                data.get("numero") or None,
                data.get("id_estado") or None,
                data.get("id_tipo") or None,
                data.get("id_stacker") or None,
                data.get("id_kit") or None,
                data.get("piso") or None,
                data.get("id_progresivo") or None,
                data.get("serie") or None,
            ),
        )
        return jsonify(ok=bool(ok), msg="Creado" if ok else "Error al crear")
    except Exception as e:
        print("DB create error: ", e)
        return jsonify(ok=False, msg="Error al crear"), 500


@app.route("/api/maquinas/<int:id>", methods=["PUT"])
def api_maquina_actualizar(id: int):
    if not is_admin():
        return jsonify(ok=False, msg="No autorizado"), 403

    data = request.get_json() or {}
    ok = exec_sql(
        "UPDATE maquinas SET id_modelo=%s, numero=%s, id_estado=%s, id_tipo=%s, id_stacker=%s, id_kit=%s, piso=%s, id_progresivo=%s, serie=%s WHERE id_maquina=%s",
        (
            data.get("id_modelo") or None,
            data.get("numero") or None,
            data.get("id_estado") or None,
            data.get("id_tipo") or None,
            data.get("id_stacker") or None,
            data.get("id_kit") or None,
            data.get("piso") or None,
            data.get("id_progresivo") or None,
            data.get("serie") or None,
            id,
        ),
    )
    return jsonify(ok=bool(ok), msg="Actualizado" if ok else "Error al actualizar")


@app.route("/api/maquinas/<int:id>", methods=["DELETE"])
def api_maquina_eliminar(id: int):
    if not is_admin():
        return jsonify(ok=False, msg="No autorizado"), 403
    try:
        ok = exec_sql("DELETE FROM maquinas WHERE id_maquina=%s", (id,))
        return jsonify(ok=bool(ok), msg="Eliminado" if ok else "No eliminado")
    except Exception as e:
        print("DB error:", e)
        return jsonify(ok=False, msg="No se puede eliminar: hay datos relacionados"), 400


# -----------------------------
# Sección: Configuración (vistas y API genérico)
# -----------------------------
# Incluimos 'estado' y 'usuarios' y demás
RESOURCE_MAP = {
    "estado": {"table": "estado", "id": "id_estado", "fields": ["estado"]},
    "kit_wigos": {"table": "kit_wigos", "id": "id_kit", "fields": ["name_kit"]},
    "modelos": {"table": "modelos", "id": "id_modelo", "fields": ["name_modelo", "id_proveedor"]},
    "progresivos": {"table": "progresivos", "id": "id_progresivo", "fields": ["name_progresivo"]},
    "proveedores": {"table": "proveedores", "id": "id_proveedor", "fields": ["name_proveedor"]},
    "tipo_jackpots": {"table": "tipo_jackpots", "id": "id_tipo", "fields": ["name_jackpot"]},
    "tipo_stacker": {"table": "tipo_stacker", "id": "id_stacker", "fields": ["name_stacker"]},
    "usuarios": {"table": "usuarios", "id": "id_usuario", "fields": ["name_usuario", "rol", "pass_usuario"]},
}


@app.route("/configuracion")
def configuracion():
    if not is_logged_in():
        return redirect(url_for("login"))
    if not is_admin():
        flash("Acceso denegado: se requiere rol Admin")
        return redirect(url_for("inicio"))

    # Consultas que devuelven los nombres relacionados donde corresponde
    kit_wigos = query_todos("SELECT id_kit, name_kit FROM kit_wigos ORDER BY id_kit")
    modelos = query_todos(
        "SELECT m.id_modelo, m.name_modelo, m.id_proveedor, p.name_proveedor FROM modelos m LEFT JOIN proveedores p ON m.id_proveedor = p.id_proveedor ORDER BY m.name_modelo"
    )
    progresivos = query_todos("SELECT id_progresivo, name_progresivo FROM progresivos ORDER BY name_progresivo")
    proveedores = query_todos("SELECT id_proveedor, name_proveedor FROM proveedores ORDER BY name_proveedor")
    tipo_jackpots = query_todos("SELECT id_tipo, name_jackpot FROM tipo_jackpots ORDER BY id_tipo")
    tipo_stacker = query_todos("SELECT id_stacker, name_stacker FROM tipo_stacker ORDER BY id_stacker")
    usuarios = query_todos("SELECT id_usuario, name_usuario, rol FROM usuarios ORDER BY name_usuario")
    estados = query_todos("SELECT id_estado, estado FROM estado ORDER BY id_estado")

    return render_template(
        "configuracion.html",
        usuario=session["usuario"],
        rol=session["rol"],
        kit_wigos=kit_wigos,
        modelos=modelos,
        progresivos=progresivos,
        proveedores=proveedores,
        tipo_jackpots=tipo_jackpots,
        tipo_stacker=tipo_stacker,
        usuarios=usuarios,
        estados=estados,
    )


# Endpoints genéricos para crear/actualizar/eliminar recursos de configuración
@app.route("/api/<resource>", methods=["POST"])
def api_config_create(resource):
    if not is_admin():
        return jsonify(ok=False, msg="No autorizado"), 403
    spec = RESOURCE_MAP.get(resource)
    if not spec:
        return jsonify(ok=False, msg="Recurso desconocido"), 404

    data = request.get_json() or {}
    cols = []
    vals = []
    for f in spec["fields"]:
        if f == "pass_usuario":
            p = data.get("pass_usuario")
            if p:
                hashed = bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                cols.append(f)
                vals.append(hashed)
            else:
                # En creación, si no pasas contraseña la rechazamos
                return jsonify(ok=False, msg="pass_usuario requerido al crear usuario"), 400
        else:
            if f in data:
                cols.append(f)
                vals.append(data.get(f))

    if not cols:
        return jsonify(ok=False, msg="No hay campos para insertar"), 400

    placeholders = ",".join(["%s"] * len(cols))
    cols_sql = ",".join(cols)
    sql = f"INSERT INTO {spec['table']} ({cols_sql}) VALUES ({placeholders})"
    ok = exec_sql(sql, tuple(vals))
    return jsonify(ok=bool(ok), msg="Creado" if ok else "Error al crear")


@app.route("/api/<resource>/<int:id>", methods=["PUT"])
def api_config_update(resource, id):
    if not is_admin():
        return jsonify(ok=False, msg="No autorizado"), 403
    spec = RESOURCE_MAP.get(resource)
    if not spec:
        return jsonify(ok=False, msg="Recurso desconocido"), 404

    data = request.get_json() or {}
    sets = []
    params = []
    for f in spec["fields"]:
        if f == "pass_usuario":
            p = data.get("pass_usuario")
            # Requisito: si no se ingresa nada en password al modificar, no se cambia
            if p:
                hashed = bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                sets.append(f + "=%s")
                params.append(hashed)
            else:
                # omitimos el campo si viene vacío o no viene
                continue
        else:
            if f in data:
                sets.append(f + "=%s")
                params.append(data.get(f))

    if not sets:
        return jsonify(ok=False, msg="No hay campos para actualizar"), 400

    params.append(id)
    sets_sql = ", ".join(sets)
    sql = f"UPDATE {spec['table']} SET {sets_sql} WHERE {spec['id']}=%s"
    ok = exec_sql(sql, tuple(params))
    return jsonify(ok=bool(ok), msg="Actualizado" if ok else "Error al actualizar")


@app.route("/api/<resource>/<int:id>", methods=["DELETE"])
def api_config_delete(resource, id):
    if not is_admin():
        return jsonify(ok=False, msg="No autorizado"), 403
    spec = RESOURCE_MAP.get(resource)
    if not spec:
        return jsonify(ok=False, msg="Recurso desconocido"), 404
    try:
        ok = exec_sql(f"DELETE FROM {spec['table']} WHERE {spec['id']}=%s", (id,))
        return jsonify(ok=bool(ok), msg="Eliminado" if ok else "No eliminado")
    except Exception as e:
        print("DB error:", e)
        return jsonify(ok=False, msg="No se puede eliminar: hay datos relacionados"), 400


#  ---  Tipo de cambio ---

from datetime import date

@app.route('/cambio')
def cambio():
    if not is_logged_in():
        return redirect(url_for('login'))

    fecha_actual = date.today()
    meses = [
        "Enero","Febrero","Marzo","Abril","Mayo","Junio",
        "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre",
    ]
    anio = fecha_actual.year
    mes_num = fecha_actual.month
    mes = meses[mes_num - 1]  # 👈 string

    tipo_cambio_actual = query_uno("""
        SELECT id_cambio, anio, mes, valor_cambio
        FROM tipo_cambio
        WHERE anio = %s AND mes = %s
        LIMIT 1
    """, (anio, mes)) or {"anio": anio, "mes": mes, "valor_cambio": "-"}


    lista_cambios = query_todos("""
        SELECT id_cambio, anio, mes, valor_cambio
        FROM tipo_cambio
        ORDER BY anio::int DESC, id_cambio DESC
    """)

    return render_template(
        'cambio.html',
        usuario=session['usuario'],
        rol=session.get('rol'),
        fecha_actual=fecha_actual.strftime('%d-%m-%Y'),
        tipo_cambio_actual=tipo_cambio_actual,
        tipo_cambio=lista_cambios,
        mes_num=mes_num,
        mes=mes
    )


@app.route('/api/tipo_cambio/<int:id_cambio>', methods=['GET'])
def api_tipo_cambio_detalle(id_cambio):
    if not is_logged_in():
        return jsonify({'ok': False, 'msg': 'No autenticado'}), 401
    row = query_uno("""
        SELECT id_cambio, anio, mes, valor_cambio
        FROM tipo_cambio
        WHERE id_cambio = %s
    """, (id_cambio,))
    if not row:
        return jsonify({'ok': False, 'msg': 'No encontrado'}), 404
    return jsonify(row)

@app.route('/api/tipo_cambio', methods=['POST'])
def api_tipo_cambio_crear():
    if not is_logged_in():
        return jsonify({'ok': False, 'msg': 'No autenticado'}), 401
    if not is_admin():
        return jsonify({'ok': False, 'msg': 'Solo Admin puede crear'}), 403

    data = request.get_json(silent=True) or {}
    try:
        anio  = int(data.get('anio'))
        valor = float(data.get('valor_cambio'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'msg': 'Campos requeridos: anio, valor_cambio'}), 400

    mes_in = data.get('mes')
    mes = normaliza_mes_nombre(mes_in)
    if not mes:
        return jsonify({'ok': False, 'msg': 'Mes inválido. Usa Enero..Diciembre'}), 400

    # Evitar duplicado (anio, mes) - ahora mes es string
    dup = query_uno("SELECT id_cambio FROM tipo_cambio WHERE anio=%s AND mes=%s LIMIT 1", (anio, mes))
    if dup:
        return jsonify({'ok': False, 'msg': 'Ya existe un tipo de cambio para ese año/mes'}), 409

    ok, last_id = exec_sql_returning(
        """
        INSERT INTO tipo_cambio(anio, mes, valor_cambio)
        VALUES (%s, %s, %s)
        RETURNING id_cambio
        """,
        (anio, mes, valor),
    )
    return (jsonify({'ok': True, 'id': last_id})
            if ok else (jsonify({'ok': False, 'msg': 'Error al crear'}), 500))



@app.route('/api/tipo_cambio/<int:id_cambio>', methods=['PUT'])
def api_tipo_cambio_actualizar(id_cambio):
    if not is_logged_in():
        return jsonify({'ok': False, 'msg': 'No autenticado'}), 401
    if not is_admin():
        return jsonify({'ok': False, 'msg': 'Solo Admin puede actualizar'}), 403

    data = request.get_json(silent=True) or {}
    try:
        anio  = int(data.get('anio'))
        valor = float(data.get('valor_cambio'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'msg': 'Campos requeridos: anio, valor_cambio'}), 400

    mes_in = data.get('mes')
    mes = normaliza_mes_nombre(mes_in)
    if not mes:
        return jsonify({'ok': False, 'msg': 'Mes inválido. Usa Enero..Diciembre'}), 400

    curr = query_uno("SELECT id_cambio FROM tipo_cambio WHERE id_cambio=%s", (id_cambio,))
    if not curr:
        return jsonify({'ok': False, 'msg': 'No encontrado'}), 404

    dup = query_uno("""
        SELECT id_cambio FROM tipo_cambio
        WHERE anio=%s AND mes=%s AND id_cambio <> %s
        LIMIT 1
    """, (anio, mes, id_cambio))
    if dup:
        return jsonify({'ok': False, 'msg': 'Ya existe un tipo de cambio para ese año/mes'}), 409

    ok, _ = exec_sql_returning("""
        UPDATE tipo_cambio
        SET anio=%s, mes=%s, valor_cambio=%s
        WHERE id_cambio=%s
        RETURNING id_cambio
    """, (anio, mes, valor, id_cambio))
    return jsonify({'ok': bool(ok)})



@app.route('/api/tipo_cambio/<int:id_cambio>', methods=['DELETE'])
def api_tipo_cambio_eliminar(id_cambio):
    if not is_logged_in():
        return jsonify({'ok': False, 'msg': 'No autenticado'}), 401
    if not is_admin():
        return jsonify({'ok': False, 'msg': 'Solo Admin puede eliminar'}), 403
    curr = query_uno("SELECT id_cambio FROM tipo_cambio WHERE id_cambio=%s", (id_cambio,))
    if not curr:
        return jsonify({'ok': False, 'msg': 'No encontrado'}), 404
    ok, _ = exec_sql_returning("DELETE FROM tipo_cambio WHERE id_cambio=%s RETURNING id_cambio", (id_cambio,))
    return jsonify({'ok': bool(ok)})

# --- Gastos ---

@app.route('/gastos')
def gastos():
    if not is_logged_in():
        return redirect(url_for('login'))

    # Parámetros de filtro
    anio = request.args.get('anio')        # '2025' o ''/None
    mes  = request.args.get('mes')         # 'Enero'..'Diciembre' o ''/None o 'Todos'
    modelo_id = request.args.get('modelo') # id_modelo o ''/None

    # Catálogos para selects
    modelos = query_todos("SELECT id_modelo, name_modelo FROM modelos ORDER BY name_modelo")
    # Años existentes en gastos
    anios = query_todos("""
        SELECT DISTINCT EXTRACT(YEAR FROM fecha)::int AS anio
        FROM gastos
        ORDER BY anio DESC
    """)
    # --- Catálogo de meses para mapping nombre -> número ---
    MESES_NOMBRE = [
        "Enero","Febrero","Marzo","Abril","Mayo","Junio",
        "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
    ]

    # ------------------ Filtros ------------------
    where = []
    params = []

    # Año
    if anio:
        where.append("EXTRACT(YEAR FROM g.fecha)::int = %s")
        params.append(int(anio))

    # Mes (nombre -> número)
    if mes and mes != "Todos":
        mes_norm = (mes or "").strip().capitalize()
        mes_num = None
        try:
            mes_num = MESES_NOMBRE.index(mes_norm) + 1  # 1..12
        except ValueError:
            mes_num = None

        if mes_num:
            where.append("EXTRACT(MONTH FROM g.fecha)::int = %s")
            params.append(mes_num)
        # si no mapea, simplemente no añadimos filtro de mes

    # Modelo
    if modelo_id:
        where.append("mo.id_modelo = %s")
        params.append(int(modelo_id))

    # ... código anterior para filtros ...
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # Consulta principal (tabla)
    gastos_list = query_todos(f"""
        SELECT
        g.id_gasto,
        g.fecha,
        g.monto,
        g.detalle,
        m.id_maquina,
        m.numero AS maquina_numero,
        mo.id_modelo,
        mo.name_modelo,
        pr.name_proveedor
        FROM gastos g
        JOIN maquinas m  ON m.id_maquina = g.id_maquina
        LEFT JOIN modelos mo ON mo.id_modelo = m.id_modelo
        LEFT JOIN proveedores pr ON pr.id_proveedor = mo.id_proveedor
        {where_sql}
        ORDER BY g.fecha DESC, g.id_gasto DESC
        LIMIT 5000
    """, tuple(params))

    #maquinas
    maquinas = query_todos("SELECT id_maquina, numero FROM maquinas ORDER BY numero")

    # >>> NUEVO: total filtrado
    total_gastos = query_valor(f"""
        SELECT COALESCE(SUM(g.monto), 0)
        FROM gastos g
        JOIN maquinas m  ON m.id_maquina = g.id_maquina
        LEFT JOIN modelos mo ON mo.id_modelo = m.id_modelo
        {where_sql}
    """, tuple(params)) or 0.0

    # Para selects (pre-selección)
    anio_sel = str(anio) if anio else ""
    mes_sel = mes if mes else ""
    modelo_sel = str(modelo_id) if modelo_id else ""

    return render_template(
        'gastos.html',
        usuario=session['usuario'],
        rol=session.get('rol'),
        modelos=modelos,
        anios=[r['anio'] for r in anios],
        meses=MESES_NOMBRE,
        gastos=gastos_list,
        anio_sel=anio_sel,
        mes_sel=mes_sel,
        modelo_sel=modelo_sel,
        total_gastos=total_gastos,   # <<< pásalo al template
        maquinas=maquinas
)


@app.route('/api/gastos/<int:id_gasto>', methods=['GET'])
def api_gasto_detalle(id_gasto):
    if not is_logged_in():
        return jsonify({'ok': False, 'msg':'No autenticado'}), 401

    row = query_uno("""
        SELECT 
          g.id_gasto,
          g.id_maquina AS id_maquina,
          TO_CHAR(g.fecha, 'YYYY-MM-DD') AS fecha,
          g.detalle,
          g.monto
        FROM gastos g
        WHERE g.id_gasto = %s
    """, (id_gasto,))

    if not row:
        return jsonify({'ok': False, 'msg':'No encontrado'}), 404

    return jsonify(row)


@app.route('/api/gastos', methods=['POST'])
def api_gasto_crear():
    if not is_logged_in():
        return jsonify({'ok': False, 'msg':'No autenticado'}), 401
    # "Administrador" puede crear; Admin también
    if session.get('rol') not in ('Administrador', 'Admin'):
        return jsonify({'ok': False, 'msg':'No autorizado'}), 403

    data = request.get_json(silent=True) or {}
    maquina = data.get('maquina')  # id_maquina
    detalle = (data.get('detalle') or '').strip()
    fecha = parse_date(data.get('fecha'))
    monto = parse_float(data.get('monto'))

    if not (maquina and detalle and fecha and monto is not None):
        return jsonify({'ok': False, 'msg':'Campos requeridos: maquina, detalle, fecha, monto'}), 400

    ok, last_id = exec_sql_returning("""
        INSERT INTO gastos (id_maquina, detalle, fecha, monto)
        VALUES (%s, %s, %s, %s)
        RETURNING id_gasto
    """, (int(maquina), detalle, fecha, monto))
    return (jsonify({'ok': True, 'id': last_id})
            if ok else (jsonify({'ok': False, 'msg':'Error al crear'}), 500))

@app.route('/api/gastos/<int:id_gasto>', methods=['PUT'])
def api_gasto_actualizar(id_gasto):
    if not is_logged_in():
        return jsonify({'ok': False, 'msg':'No autenticado'}), 401
    # "Administrador" NO puede editar; solo Admin
    if session.get('rol') != 'Admin':
        return jsonify({'ok': False, 'msg':'Solo Admin puede modificar'}), 403

    data = request.get_json(silent=True) or {}
    maquina = data.get('maquina')
    detalle = (data.get('detalle') or '').strip()
    fecha = parse_date(data.get('fecha'))
    monto = parse_float(data.get('monto'))

    if not (maquina and detalle and fecha and monto is not None):
        return jsonify({'ok': False, 'msg':'Campos requeridos: maquina, detalle, fecha, monto'}), 400

    ok, _ = exec_sql_returning("""
        UPDATE gastos
        SET id_maquina=%s, detalle=%s, fecha=%s, monto=%s
        WHERE id_gasto=%s
        RETURNING id_gasto
    """, (int(maquina), detalle, fecha, monto, id_gasto))
    return jsonify({'ok': bool(ok)})

@app.route('/api/gastos/<int:id_gasto>', methods=['DELETE'])
def api_gasto_eliminar(id_gasto):
    if not is_logged_in():
        return jsonify({'ok': False, 'msg':'No autenticado'}), 401
    # "Administrador" NO puede eliminar; solo Admin
    if session.get('rol') != 'Admin':
        return jsonify({'ok': False, 'msg':'Solo Admin puede eliminar'}), 403

    ok, _ = exec_sql_returning(
        "DELETE FROM gastos WHERE id_gasto=%s RETURNING id_gasto",
        (id_gasto,)
    )
    return jsonify({'ok': bool(ok)})


#-------------
# --- HOLD ---


@app.route('/api/hold/preview', methods=['POST'])
def api_hold_preview():
    if not is_logged_in():
        return jsonify({'ok': False, 'msg': 'No autenticado'}), 401

    f = request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'msg': 'Adjunta un archivo .xlsx/.xls'}), 400

    filename = (f.filename or '').lower()
    if not (filename.endswith('.xlsx') or filename.endswith('.xls')):
        return jsonify({'ok': False, 'msg': 'Formato no admitido. Usa .xlsx o .xls'}), 400

    # Import local para evitar fallos si falta pandas en otros endpoints
    try:
        import pandas as pd
    except Exception:
        return jsonify({'ok': False, 'msg': 'Falta librería pandas en el servidor'}), 500

    try:
        # Leer Excel con heurística de engine
        if filename.endswith('.xlsx'):
            df = pd.read_excel(f, engine='openpyxl')
        else:
            # .xls -> intenta inferir; si no, xlrd
            try:
                df = pd.read_excel(f)
            except Exception:
                df = pd.read_excel(f, engine='xlrd')

        # 1) Eliminar filas 1..5 (índices 0..4). Ajusta si tu archivo tiene otro offset.
        df = df.drop(df.index[0:5])

        # 2) Eliminar primeras 2 columnas por índice (si existen)
        if df.shape[1] >= 2:
            df = df.drop(df.columns[[0, 1]], axis=1)

        # 2b) Eliminar columnas "Unnamed: x" específicas si existen
        for col in ['Unnamed: 3','Unnamed: 7','Unnamed: 9','Unnamed: 19','Unnamed: 22',
                    'Unnamed: 26','Unnamed: 28','Unnamed: 29','Unnamed: 30','Unnamed: 31','Unnamed: 32']:
            if col in df.columns:
                df = df.drop(columns=[col], axis=1)

        # 3) Primera fila como encabezado
        df.columns = df.iloc[0]
        df = df[1:].reset_index(drop=True)

        # 4) Quitar filas en blanco columna 'Jornada'
        if 'Jornada' in df.columns:
            df = df[df['Jornada'].notna()]

        # 5) Quitar filas en blanco columna 'Máquina'
        if 'Máquina' in df.columns:
            df = df[df['Máquina'].notna()]

        # 6) Renombrar columnas al conjunto final (orden exacto esperado por tu DB)
        #    Asegúrate de que el número de columnas coincida; si no, revisa tu plantilla Excel.
        df.columns = [
            'maquina','jornada','jugado','ganado','bill','in_redimibles','promo_in_no_redimible','promo_redimible',
            'out_redimible','promo_out_no_redimible','jackpot','salida_manual','total_in','total_out','total_re_in',
            'total_re_out','jugadas','apuesta_media','jugadas_ganadas','promo_no_redimible'
        ]

        # 7) Reemplazar NaN por None
        df = df.where(df.notnull(), None)

        # Devolver preview
        rows = df.to_dict(orient='records')
        cols = list(df.columns)
        return jsonify({'ok': True, 'columns': cols, 'rows': rows})
    except Exception as e:
        print("preview error:", e)
        return jsonify({'ok': False, 'msg': 'Error procesando el Excel'}), 500


# ================================================
#  INSERT: inserta filas nuevas (evita duplicados)
# ================================================
@app.route('/api/hold/insert', methods=['POST'])
def api_hold_insert():
    if not is_logged_in():
        return jsonify({'ok': False, 'msg': 'No autenticado'}), 401

    # Si no usas roles, comenta este bloque:
    if session.get('rol') != 'Admin':
        return jsonify({'ok': False, 'msg': 'Solo Admin puede insertar'}), 403

    data = request.get_json(silent=True) or {}
    rows = data.get('rows') or []
    if not rows:
        return jsonify({'ok': False, 'msg': 'No hay datos para insertar'}), 400

    # Normalizadores
    def numf(x):
        if x in (None, '', 'NaN'):
            return None
        try:
            return float(str(x).replace(',', ''))
        except Exception:
            return None

    def numi(x):
        if x in (None, '', 'NaN'):
            return None
        try:
            return int(float(str(x).replace(',', '')))
        except Exception:
            return None

    def strn(x):
        x = (x or '').strip()
        return x or None

    conn = conectar_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT maquina, jornada FROM datos")
            existentes = set((m or '', j or '') for (m, j) in cur.fetchall())

        values = []
        skipped = 0

        for r in rows:
            maquina = strn(r.get('maquina'))
            jornada = strn(r.get('jornada'))
            if not (maquina and jornada):
                skipped += 1
                continue
            key = (maquina, jornada)
            if key in existentes:
                skipped += 1
                continue

            values.append((
                maquina,
                jornada,
                numf(r.get('jugado')),
                numf(r.get('ganado')),
                numi(r.get('bill')),
                numi(r.get('in_redimibles')),      # DF plural -> DB singular
                numi(r.get('promo_in_no_redimible')),
                numf(r.get('promo_redimible')),
                numf(r.get('out_redimible')),
                numf(r.get('promo_out_no_redimible')),
                numf(r.get('jackpot')),
                numf(r.get('salida_manual')),
                numf(r.get('total_in')),
                numf(r.get('total_out')),
                numf(r.get('total_re_in')),
                numf(r.get('total_re_out')),
                numi(r.get('jugadas')),
                numf(r.get('apuesta_media')),
                numi(r.get('jugadas_ganadas')),
                numi(r.get('promo_no_redimible')),
            ))

        if not values:
            return jsonify({'ok': True, 'inserted': 0, 'skipped': skipped})

        from psycopg2.extras import execute_values
        sql = """
          INSERT INTO datos
          (maquina, jornada, jugado, ganado, bill, in_redimible, promo_in_no_redimible,
           promo_redimible, out_redimible, promo_out_no_redimible, jackpot, salida_manual,
           total_in, total_out, total_re_in, total_re_out, jugadas, apuesta_media,
           jugadas_ganadas, promo_no_redimible)
          VALUES %s
        """
        with conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, values, page_size=1000)

        return jsonify({'ok': True, 'inserted': len(values), 'skipped': skipped})

    except Exception as e:
        print("insert error:", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return jsonify({'ok': False, 'msg': 'Error al insertar'}), 500
    finally:
        conn.close()



from datetime import date
from flask import request, redirect, url_for

MESES_NOMBRE = [
    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
]

from datetime import date
from flask import request, redirect, url_for

MESES_NOMBRE = [
    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
]

@app.route('/hold')
def hold():
    if not is_logged_in():
        return redirect(url_for('login'))

    anio      = request.args.get('anio', type=int)
    mes       = request.args.get('mes',  type=int)
    dia       = request.args.get('dia',  type=int)
    modelo_id = request.args.get('modelo_id', type=int)

    # Usa el helper central para calcular todo el contexto
    ctx = get_hold_context(anio, mes, dia, modelo_id)
    return render_template("hold.html", **ctx)


@app.route('/api/hold/data', methods=['GET'])
def hold_data():
    if not is_logged_in():
        return jsonify({'ok': False, 'msg': 'No autorizado'}), 401

    anio      = request.args.get('anio', type=int)
    mes       = request.args.get('mes',  type=int)
    dia       = request.args.get('dia',  type=int)
    modelo_id = request.args.get('modelo_id', type=int)

    ctx = get_hold_context(anio, mes, dia, modelo_id)

    # Normaliza a JSON seguro (por si vinieran Decimal/fechas)
    def norm(x):
        if isinstance(x, dict):
            return {k: norm(v) for k, v in x.items()}
        if isinstance(x, list):
            return [norm(v) for v in x]
        if isinstance(x, (date, datetime)):
            return x.strftime('%Y-%m-%d')
        if isinstance(x, Decimal):
            return float(x)
        return x

    return jsonify({'ok': True, 'data': norm(ctx)})





# =========================
# Helper: contexto para HOLD (JSON + Template)
# =========================
def get_hold_context(anio=None, mes=None, dia=None, modelo_id=None):
    if not is_logged_in():
        return {}

    hoy = date.today()
    anio_hoy = hoy.year
    mes_hoy_num = hoy.month

    # Filtros efectivos
    anio_sel   = anio or anio_hoy
    mes_sel    = mes  or mes_hoy_num
    dia_sel    = dia
    modelo_sel = modelo_id

    base_cte = """
      WITH dts AS (
        SELECT d.*,
               to_timestamp(d.jornada, 'DD/MM/YYYY HH24:MI') AS tstamp
        FROM datos d
      )
    """

    # Años disponibles
    anios_rows = query_todos(base_cte + """
        SELECT DISTINCT EXTRACT(YEAR FROM tstamp)::int AS anio
        FROM dts
        WHERE tstamp IS NOT NULL
        ORDER BY 1 DESC
    """)
    anios_disponibles = [r['anio'] for r in anios_rows]
    if anio_hoy not in anios_disponibles:
        anios_disponibles = [anio_hoy] + anios_disponibles

    # Meses disponibles
    meses_rows = query_todos(base_cte + """
        SELECT DISTINCT EXTRACT(MONTH FROM tstamp)::int AS mes
        FROM dts
        WHERE tstamp IS NOT NULL
          AND EXTRACT(YEAR FROM tstamp)::int = %s
        ORDER BY 1
    """, (anio_sel,))
    meses_disponibles = [r['mes'] for r in meses_rows]
    if anio_sel == anio_hoy and mes_hoy_num not in meses_disponibles:
        meses_disponibles = [mes_hoy_num] + meses_disponibles
    if meses_disponibles and mes_sel not in meses_disponibles:
        mes_sel = mes_hoy_num if mes_hoy_num in meses_disponibles else meses_disponibles[0]

    # Días disponibles
    dias_rows = query_todos(base_cte + """
        SELECT DISTINCT EXTRACT(DAY FROM tstamp)::int AS dia
        FROM dts
        WHERE tstamp IS NOT NULL
          AND EXTRACT(YEAR FROM tstamp)::int = %s
          AND EXTRACT(MONTH FROM tstamp)::int = %s
        ORDER BY 1
    """, (anio_sel, mes_sel))
    dias_disponibles = [r['dia'] for r in dias_rows]
    if dia_sel and dias_disponibles and dia_sel not in dias_disponibles:
        dia_sel = None  # "Todos"

    # Tipo de cambio (tu DB guarda el mes como texto)
    mes_sel_nombre = MESES_NOMBRE[mes_sel - 1]
    tipo_cambio_actual = query_uno("""
        SELECT id_cambio, anio, mes, valor_cambio
        FROM tipo_cambio
        WHERE anio = %s AND mes = %s
        LIMIT 1
    """, (anio_sel, mes_sel_nombre)) or {
        "anio": anio_sel, "mes": mes_sel_nombre, "valor_cambio": "-"
    }
    tc_val = _to_float(tipo_cambio_actual.get('valor_cambio')) if isinstance(tipo_cambio_actual, dict) else None

    # ====== 1) KPIs GLOBALES (solo Año/Mes) ======
    where_kpi = (
        " WHERE tstamp IS NOT NULL "
        " AND EXTRACT(YEAR FROM tstamp)::int = %s "
        " AND EXTRACT(MONTH FROM tstamp)::int = %s "
    )
    params_kpi = [anio_sel, mes_sel]

    ingreso_total = _to_float(query_valor(base_cte + f"""
        SELECT COALESCE(SUM(total_in),0)
        FROM dts
        {where_kpi}
    """, tuple(params_kpi))) or 0.0

    win_total = _to_float(query_valor(base_cte + f"""
        SELECT COALESCE(SUM(total_in - total_out),0)
        FROM dts
        {where_kpi}
    """, tuple(params_kpi))) or 0.0

    dias_periodo_t = query_valor(base_cte + f"""
        SELECT COUNT(DISTINCT DATE(tstamp))
        FROM dts
        {where_kpi}
    """, tuple(params_kpi)) or 0

    maquinas_distintas_kpi = query_valor(base_cte + f"""
        SELECT COUNT(DISTINCT maquina)
        FROM dts
        {where_kpi} AND COALESCE(jugado,0) > 0
    """, tuple(params_kpi)) or 0

    prom_dias_jugado_pos_t = query_valor(base_cte + f"""
        SELECT COALESCE(AVG(sub.cnt), 0)
        FROM (
        SELECT d.maquina, COUNT(DISTINCT DATE(d.tstamp)) AS cnt
        FROM dts d
        JOIN maquinas m 
            ON regexp_replace(btrim(lower(m.numero::text)),'[^0-9a-z]+','','g')
            = regexp_replace(btrim(lower(d.maquina::text)),'[^0-9a-z]+','','g')
        {where_kpi} AND COALESCE(d.jugado,0) > 0
        GROUP BY d.maquina
        ) sub
    """, params_kpi) or 0.0

    prom_dias_jugado_pos_t = _to_float(prom_dias_jugado_pos_t) or 0.0

    avg_net_in = avg_net_win = net_in_diario = net_win_diario = retencion = 0.0
    if tc_val and dias_periodo_t and maquinas_distintas_kpi:
        avg_net_in  = _safe_div(_safe_div(ingreso_total, dias_periodo_t), tc_val)
        avg_net_in  = _safe_div(avg_net_in, maquinas_distintas_kpi)
        avg_net_win = _safe_div(_safe_div(win_total,     dias_periodo_t), tc_val)
        avg_net_win = _safe_div(avg_net_win, maquinas_distintas_kpi)

    if tc_val and prom_dias_jugado_pos_t and maquinas_distintas_kpi:
        net_in_diario  = _safe_div(_safe_div(ingreso_total, prom_dias_jugado_pos_t), tc_val)
        net_in_diario  = _safe_div(net_in_diario, maquinas_distintas_kpi)
        net_win_diario = _safe_div(_safe_div(win_total,     prom_dias_jugado_pos_t), tc_val)
        net_win_diario = _safe_div(net_win_diario, maquinas_distintas_kpi)

    if ingreso_total:
        retencion = _safe_div(win_total, ingreso_total) * 100.0

    # ====== 2) BLOQUE FILTRABLE (Año, Mes, Día?, Modelo?) ======
    # where_mes_anio: SOLO A/M (para días del período)
    where_mes_anio = where_kpi
    params_mes_anio = list(params_kpi)

    # where_periodo: A/M + (opcional) Día
    where_periodo = where_kpi
    params_periodo = list(params_kpi)
    if dia_sel:
        where_periodo += " AND EXTRACT(DAY FROM tstamp)::int = %s "
        params_periodo.append(dia_sel)

    # where_join: (periodo) + (opcional) modelo — JOIN normalizado m.numero ↔ d.maquina
    where_join = where_periodo
    params_join = list(params_periodo)
    if modelo_sel:
        where_join += " AND m.id_modelo = %s "
        params_join.append(modelo_sel)
    params_join = tuple(params_join)

    prom_dias_jugado_pos = query_valor(base_cte + f"""
        SELECT COALESCE(AVG(sub.cnt), 0)
        FROM (
          SELECT maquina, COUNT(DISTINCT DATE(tstamp)) AS cnt
          FROM dts
          {where_periodo} AND COALESCE(jugado,0) > 0
          GROUP BY maquina
        ) sub
    """, tuple(params_periodo)) or 0.0
    prom_dias_jugado_pos = _to_float(prom_dias_jugado_pos) or 0.0

    # Máquinas distintas (A/M; jugado>0) usando clave normalizada en dts
    maquinas_distintas = query_valor(base_cte + f"""
        SELECT COUNT(
            DISTINCT regexp_replace(btrim(lower(d.maquina::text)),'[^0-9a-z]+','','g')
        )
        FROM dts d
        {where_kpi} AND COALESCE(d.jugado,0) > 0
    """, tuple(params_kpi)) or 0

    # Máquinas activas (A/M[/D][/Modelo]; jugado>0) con JOIN normalizado
    maquinas_activas_hold = query_valor(base_cte + f"""
        SELECT COUNT(DISTINCT m.id_maquina)
        FROM dts d
        JOIN maquinas m 
          ON regexp_replace(btrim(lower(m.numero::text)),'[^0-9a-z]+','','g')
           = regexp_replace(btrim(lower(d.maquina::text)),'[^0-9a-z]+','','g')
        {where_join} AND COALESCE(d.jugado,0) > 0
    """, params_join) or 0

    # Días del período (solo A/M)
    dias_periodo = query_valor(base_cte + f"""
        SELECT COUNT(DISTINCT DATE(tstamp))
        FROM dts
        {where_mes_anio}
    """, tuple(params_mes_anio)) or 0

    # Totales (IN y WIN) bajo filtros — JOIN normalizado
    ingreso_total_m = _to_float(query_valor(base_cte + f"""
        SELECT COALESCE(SUM(d.total_in),0)
        FROM dts d
        JOIN maquinas m 
          ON regexp_replace(btrim(lower(m.numero::text)),'[^0-9a-z]+','','g')
           = regexp_replace(btrim(lower(d.maquina::text)),'[^0-9a-z]+','','g')
        {where_join}
    """, params_join)) or 0.0

    win_total_m = _to_float(query_valor(base_cte + f"""
        SELECT COALESCE(SUM(d.total_in - d.total_out),0)
        FROM dts d
        JOIN maquinas m 
          ON regexp_replace(btrim(lower(m.numero::text)),'[^0-9a-z]+','','g')
           = regexp_replace(btrim(lower(d.maquina::text)),'[^0-9a-z]+','','g')
        {where_join}
    """, params_join)) or 0.0

    # Días con juego (>0) bajo filtros (para *_diario_m)
    dias_periodo_pos_m = query_valor(base_cte + f"""
        SELECT COALESCE(AVG(sub.cnt), 0)
        FROM (
        SELECT d.maquina, COUNT(DISTINCT DATE(d.tstamp)) AS cnt
        FROM dts d
        JOIN maquinas m 
            ON regexp_replace(btrim(lower(m.numero::text)),'[^0-9a-z]+','','g')
            = regexp_replace(btrim(lower(d.maquina::text)),'[^0-9a-z]+','','g')
        {where_join} AND COALESCE(d.jugado,0) > 0
        GROUP BY d.maquina
        ) sub
    """, params_join) or 0.0

    avg_net_in_m = net_in_diario_m = avg_net_win_m = net_win_diario_m = retencion_m = 0.0
    if tc_val and maquinas_activas_hold and dias_periodo:
        avg_net_in_m  = _safe_div(_safe_div(ingreso_total_m, maquinas_activas_hold), tc_val)
        avg_net_in_m  = _safe_div(avg_net_in_m, dias_periodo)
        avg_net_win_m = _safe_div(_safe_div(win_total_m, maquinas_activas_hold), tc_val)
        avg_net_win_m = _safe_div(avg_net_win_m, dias_periodo)

    if tc_val and maquinas_activas_hold and dias_periodo_pos_m:
        net_in_diario_m  = _safe_div(_safe_div(ingreso_total_m, dias_periodo_pos_m), tc_val)
        net_in_diario_m  = _safe_div(net_in_diario_m, maquinas_activas_hold)
        net_win_diario_m = _safe_div(_safe_div(win_total_m, dias_periodo_pos_m), tc_val)
        net_win_diario_m = _safe_div(net_win_diario_m, maquinas_activas_hold)

    if ingreso_total_m:
        retencion_m = _safe_div(win_total_m, ingreso_total_m) * 100.0

    # Sidebar de modelos
    where_sidebar_on = """
          AND EXTRACT(YEAR  FROM d.tstamp)::int = %s
          AND EXTRACT(MONTH FROM d.tstamp)::int = %s
    """
    params_sidebar = [anio_sel, mes_sel]
    if dia_sel:
        where_sidebar_on += " AND EXTRACT(DAY FROM d.tstamp)::int = %s "
        params_sidebar.append(dia_sel)

    modelos_sidebar = query_todos(base_cte + f"""
        SELECT 
            mo.id_modelo,
            mo.name_modelo,
            COUNT(DISTINCT CASE WHEN COALESCE(d.jugado,0) > 0 THEN m.id_maquina END) AS cant_maquinas_periodo
        FROM modelos mo
        LEFT JOIN maquinas m 
               ON m.id_modelo = mo.id_modelo
        LEFT JOIN dts d 
               ON regexp_replace(btrim(lower(d.maquina::text)),'[^0-9a-z]+','','g')
               =  regexp_replace(btrim(lower(m.numero::text)),'[^0-9a-z]+','','g')
              {where_sidebar_on}
        GROUP BY mo.id_modelo, mo.name_modelo
        HAVING COUNT(CASE WHEN COALESCE(d.jugado,0) > 0 THEN m.id_maquina END) > 0
        ORDER BY mo.name_modelo NULLS LAST
    """, tuple(params_sidebar))

    meses_opciones = [{"num": m, "nombre": MESES_NOMBRE[m-1]} for m in sorted(set(meses_disponibles))]

    return {
        "fecha_actual": hoy.strftime('%d-%m-%Y'),
        "tipo_cambio_actual": {
            "anio": tipo_cambio_actual["anio"],
            "mes":  tipo_cambio_actual["mes"],
            "valor_cambio": _to_float(tipo_cambio_actual.get("valor_cambio")) if isinstance(tipo_cambio_actual, dict) else tipo_cambio_actual
        },
        "anios_disponibles": anios_disponibles,
        "meses_opciones": meses_opciones,
        "dias_disponibles": dias_disponibles,
        "anio_sel": anio_sel,
        "mes_sel": mes_sel,
        "dia_sel": dia_sel,
        "modelo_sel": modelo_sel,
        "maquinas_distintas": maquinas_distintas,
        "modelos_sidebar": modelos_sidebar,
        "maquinas_activas_hold": maquinas_activas_hold,
        "dias_periodo": dias_periodo,
        "ingreso_total": ingreso_total,
        "win_total": win_total,
        "avg_net_in": avg_net_in,
        "avg_net_in_diario": 0.0,
        "net_in_diario": net_in_diario,
        "prom_dias_jugado_pos": prom_dias_jugado_pos,
        "prom_dias_jugado_pos_t": prom_dias_jugado_pos_t,
        "avg_net_win": avg_net_win,
        "net_win_diario": net_win_diario,
        "retencion": retencion,
        "ingreso_total_m": ingreso_total_m,
        "win_total_m": win_total_m,
        "dias_periodo_m": dias_periodo,
        "maquinas_distintas_m": maquinas_distintas,
        "ingreso_total_pos_m": None,
        "dias_periodo_pos_m": dias_periodo_pos_m,
        "prom_dias_jugado_pos_m": None,
        "maquinas_activas_hold_m": None,
        "avg_net_in_m": avg_net_in_m,
        "avg_net_in_diario_m": 0.0,
        "net_in_diario_m": net_in_diario_m,
        "avg_net_win_m": avg_net_win_m,
        "net_win_diario_m": net_win_diario_m,
        "retencion_m": retencion_m,
        "rol": session.get("rol"),
        "usuario": session.get("usuario"),
    }



@app.route('/__routes__')
def __routes__():
    return '<pre>' + '\n'.join(sorted(map(str, app.url_map.iter_rules()))) + '</pre>'



if __name__ == '__main__':
    app.run(debug=True)