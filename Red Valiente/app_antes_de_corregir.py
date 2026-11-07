import os
import re
import sqlite3
import hashlib
import uuid

from functools import wraps
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# ==========================================================
# 1. CONFIGURACIÓN GENERAL
# ==========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "red_valiente_clave_local_cambiar_en_produccion"
)

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

DATABASE = os.path.join(BASE_DIR, "red_valiente.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==========================================================
# 2. CONEXIÓN A SQLITE
# ==========================================================

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def agregar_columna(conn, tabla, columna, definicion):
    columnas = [
        fila["name"]
        for fila in conn.execute(f"PRAGMA table_info({tabla})").fetchall()
    ]

    if columna not in columnas:
        conn.execute(
            f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}"
        )


# ==========================================================
# 3. INICIALIZACIÓN Y ACTUALIZACIÓN DE LA BASE DE DATOS
# ==========================================================

def init_db():
    conn = get_db_connection()

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                correo TEXT UNIQUE NOT NULL,
                telefono TEXT NOT NULL,
                clave TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                pdf_soporte TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS vacantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                empresa TEXT NOT NULL,
                salario TEXT NOT NULL,
                jornada TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS postulaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuaria_id INTEGER NOT NULL,
                vacante_id INTEGER NOT NULL,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuaria_id) REFERENCES usuarias(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (vacante_id) REFERENCES vacantes(id)
            )
        """)

        # Ampliar tablas existentes sin borrar sus registros.
        agregar_columna(conn, "vacantes", "sector", "TEXT DEFAULT ''")
        agregar_columna(conn, "vacantes", "ubicacion", "TEXT DEFAULT ''")
        agregar_columna(conn, "vacantes", "descripcion", "TEXT DEFAULT ''")
        agregar_columna(conn, "vacantes", "activa", "INTEGER DEFAULT 1")

        agregar_columna(
            conn,
            "postulaciones",
            "estado",
            "TEXT DEFAULT 'Enviada'"
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS capacitaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                duracion TEXT NOT NULL,
                modalidad TEXT NOT NULL,
                categoria TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                activa INTEGER DEFAULT 1
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS inscripciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuaria_id INTEGER NOT NULL,
                curso_id INTEGER NOT NULL,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                estado TEXT DEFAULT 'Inscrita',
                FOREIGN KEY (usuaria_id) REFERENCES usuarias(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (curso_id) REFERENCES capacitaciones(id),
                UNIQUE (usuaria_id, curso_id)
            )
        """)

        # Crear administrador solamente si no existe.
        admin = conn.execute(
            "SELECT id FROM usuarias WHERE correo = ?",
            ("admin@redvaliente.org",)
        ).fetchone()

        if not admin:
            clave_admin = generate_password_hash("admin123")

            conn.execute("""
                INSERT INTO usuarias
                (nombre, correo, telefono, clave, estado)
                VALUES (?, ?, ?, ?, ?)
            """, (
                "Admin",
                "admin@redvaliente.org",
                "0000",
                clave_admin,
                "Validada"
            ))

        # Vacantes de ejemplo. INSERT OR IGNORE conserva las existentes.
        vacantes_iniciales = [
            (
                1, "Auxiliar de Enfermería", "Clínica San José",
                "$1'800.000", "Tiempo Completo", "Salud", "Bogotá",
                "Apoyo en atención a pacientes y gestión de historias clínicas."
            ),
            (
                2, "Desarrolladora Junior", "Tech Solutions",
                "$2'500.000", "Tiempo Completo", "Tecnología", "Medellín",
                "Desarrollo y mantenimiento de aplicaciones web."
            ),
            (
                3, "Atención al Cliente", "Teleperformance",
                "$1'500.000", "Horario Flexible", "Atención al Cliente",
                "Bogotá", "Gestión de soporte y canales de comunicación."
            ),
            (
                4, "Auxiliar de Cocina y Pastelería",
                "Restaurante El Sazón", "$1'400.000",
                "Tiempo Completo", "Gastronomía", "Bogotá",
                "Preparación de ingredientes y apoyo en cocina."
            ),
            (
                5, "Operario de Servicios Generales",
                "Limpio & Seguro Co.", "$1'300.000",
                "Horario Flexible", "Servicios Generales", "Medellín",
                "Mantenimiento y desinfección de áreas."
            ),
            (
                6, "Asistente Administrativa",
                "Grupo Financiero Alfa", "$2'000.000",
                "Tiempo Completo", "Administrativo", "Bogotá",
                "Organización de agenda y manejo de correspondencia."
            ),
            (
                7, "Tutora de Apoyo Escolar", "Fundación Educar",
                "$1'600.000", "Medio Tiempo", "Educación", "Remoto",
                "Acompañamiento escolar y refuerzo académico."
            ),
            (
                8, "Coordinadora de Logística e Inventarios",
                "Bodegas del Norte", "$2'200.000",
                "Tiempo Completo", "Logística", "Bogotá",
                "Control de entradas, salidas y organización de inventario."
            )
        ]

        for v in vacantes_iniciales:
            conn.execute("""
                INSERT OR IGNORE INTO vacantes
                (id, titulo, empresa, salario, jornada,
                 sector, ubicacion, descripcion, activa)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, v)

        # Completar datos de las tres vacantes antiguas si están vacíos.
        for v in vacantes_iniciales:
            conn.execute("""
                UPDATE vacantes
                SET sector = CASE
                    WHEN sector IS NULL OR sector = '' THEN ?
                    ELSE sector END,
                    ubicacion = CASE
                    WHEN ubicacion IS NULL OR ubicacion = '' THEN ?
                    ELSE ubicacion END,
                    descripcion = CASE
                    WHEN descripcion IS NULL OR descripcion = '' THEN ?
                    ELSE descripcion END
                WHERE id = ?
            """, (v[5], v[6], v[7], v[0]))

        cursos_iniciales = [
            (
                1, "Habilidades Digitales y Ofimática",
                "40 Horas", "Virtual", "Tecnología",
                "Aprende herramientas digitales y ofimáticas."
            ),
            (
                2, "Emprendimiento y Finanzas Personales",
                "30 Horas", "Presencial / Virtual", "Negocios",
                "Conoce herramientas para administrar tus finanzas."
            ),
            (
                3, "Excel Profesional para Gestión Administrativa",
                "25 Horas", "Virtual", "Herramientas",
                "Aprende Excel aplicado a tareas administrativas."
            ),
            (
                4, "Servicio al Cliente y Comunicación Asertiva",
                "20 Horas", "Virtual", "Servicios",
                "Desarrolla habilidades de comunicación y atención."
            )
        ]

        for curso in cursos_iniciales:
            conn.execute("""
                INSERT OR IGNORE INTO capacitaciones
                (id, titulo, duracion, modalidad, categoria, descripcion, activa)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, curso)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


init_db()


# ==========================================================
# 4. LISTAS PARA LOS FILTROS
# ==========================================================

SECTORES = [
    "Todos los sectores",
    "Salud",
    "Tecnología",
    "Atención al Cliente",
    "Gastronomía",
    "Servicios Generales",
    "Administrativo",
    "Educación",
    "Logística"
]

JORNADAS = [
    "Todas las jornadas",
    "Tiempo Completo",
    "Medio Tiempo",
    "Horario Flexible"
]

UBICACIONES = [
    "Todas las ubicaciones",
    "Bogotá",
    "Medellín",
    "Remoto"
]


# ==========================================================
# 5. FUNCIONES AUXILIARES Y PERMISOS
# ==========================================================

def obtener_usuaria_actual():
    correo = session.get("usuario")

    if not correo:
        return None

    conn = get_db_connection()
    usuaria = conn.execute(
        "SELECT * FROM usuarias WHERE correo = ?",
        (correo,)
    ).fetchone()
    conn.close()

    return usuaria


def login_requerido(funcion):
    @wraps(funcion)
    def decorador(*args, **kwargs):
        if "usuario" not in session:
            flash("Debes iniciar sesión para continuar.", "error")
            return redirect(url_for("login"))

        return funcion(*args, **kwargs)

    return decorador


def admin_requerido(funcion):
    @wraps(funcion)
    def decorador(*args, **kwargs):
        if (
            session.get("usuario") != "admin@redvaliente.org"
            or session.get("rol") != "admin"
        ):
            flash("No tienes permisos para acceder a esta sección.", "error")
            return redirect(url_for("login"))

        return funcion(*args, **kwargs)

    return decorador


def validar_pdf(archivo):
    if not archivo or not archivo.filename:
        return None, "Debes adjuntar tu documento PDF."

    nombre = secure_filename(archivo.filename)

    if not nombre.lower().endswith(".pdf"):
        return None, "El documento debe estar en formato PDF."

    contenido = archivo.read(5 * 1024 * 1024 + 1)
    archivo.seek(0)

    if len(contenido) > 5 * 1024 * 1024:
        return None, "El PDF no puede superar los 5 MB."

    if not contenido.startswith(b"%PDF"):
        return None, "El archivo seleccionado no parece ser un PDF válido."

    nombre_final = f"{uuid.uuid4().hex}_{nombre}"
    ruta = os.path.join(UPLOAD_FOLDER, nombre_final)

    with open(ruta, "wb") as documento:
        documento.write(contenido)

    return nombre_final, None


def eliminar_pdf(nombre):
    if not nombre:
        return

    ruta = os.path.join(UPLOAD_FOLDER, nombre)

    if os.path.isfile(ruta):
        os.remove(ruta)


def validar_datos_vacante(datos):
    campos = ["titulo", "empresa", "salario", "jornada",
              "sector", "ubicacion", "descripcion"]

    for campo in campos:
        if not datos.get(campo, "").strip():
            return f"El campo {campo} es obligatorio."

    return None


# ==========================================================
# 6. INICIO
# ==========================================================

@app.route("/")
@app.route("/inicio")
def inicio():
    if "usuario" in session:
        if session.get("rol") == "admin":
            return redirect(url_for("panel_admin"))

        return redirect(url_for("ver_empleos"))

    return redirect(url_for("login"))


# ==========================================================
# 7. INICIO DE SESIÓN
# ==========================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        clave = request.form.get("clave", "")

        if not correo or not clave:
            flash("Debes escribir tu correo y contraseña.", "error")
            return render_template("login.html")

        conn = get_db_connection()

        usuaria = conn.execute(
            "SELECT * FROM usuarias WHERE correo = ?",
            (correo,)
        ).fetchone()

        conn.close()

        acceso_correcto = False

        if usuaria:
            clave_guardada = usuaria["clave"]

            # Compatibilidad con contraseñas SHA-256 antiguas.
            if re.fullmatch(r"[a-fA-F0-9]{64}", clave_guardada or ""):
                clave_sha = hashlib.sha256(
                    clave.encode("utf-8")
                ).hexdigest()

                if clave_sha == clave_guardada:
                    acceso_correcto = True

                    nueva_clave = generate_password_hash(clave)

                    conn = get_db_connection()
                    conn.execute(
                        "UPDATE usuarias SET clave = ? WHERE id = ?",
                        (nueva_clave, usuaria["id"])
                    )
                    conn.commit()
                    conn.close()

            else:
                try:
                    acceso_correcto = check_password_hash(
                        clave_guardada,
                        clave
                    )
                except (ValueError, TypeError):
                    acceso_correcto = False

        if acceso_correcto:
            session.clear()
            session["usuario"] = usuaria["correo"]
            session["nombre"] = usuaria["nombre"]

            if usuaria["correo"] == "admin@redvaliente.org":
                session["rol"] = "admin"
                return redirect(url_for("panel_admin"))

            session["rol"] = "usuaria"
            return redirect(url_for("ver_empleos"))

        flash("Correo o contraseña incorrectos.", "error")

    return render_template("login.html")


# ==========================================================
# 8. REGISTRO DE USUARIAS
# ==========================================================

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        telefono = request.form.get("telefono", "").strip()
        clave = request.form.get("clave", "")
        confirmar_clave = request.form.get("confirmar_clave", "")

        if not all([nombre, correo, telefono, clave]):
            flash("Todos los campos obligatorios deben completarse.", "error")
            return render_template("registro.html")

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
            flash("Escribe un correo electrónico válido.", "error")
            return render_template("registro.html")

        if len(clave) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
            return render_template("registro.html")

        if confirmar_clave and clave != confirmar_clave:
            flash("Las contraseñas no coinciden.", "error")
            return render_template("registro.html")

        archivo = request.files.get("pdf_soporte")
        pdf_filename, error_pdf = validar_pdf(archivo)

        if error_pdf:
            flash(error_pdf, "error")
            return render_template("registro.html")

        clave_encriptada = generate_password_hash(clave)

        conn = get_db_connection()

        try:
            conn.execute("""
                INSERT INTO usuarias
                (nombre, correo, telefono, clave, estado, pdf_soporte)
                VALUES (?, ?, ?, ?, 'Pendiente', ?)
            """, (
                nombre,
                correo,
                telefono,
                clave_encriptada,
                pdf_filename
            ))

            conn.commit()

            flash(
                "¡Registro exitoso! Tu cuenta está pendiente de aprobación.",
                "success"
            )

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            conn.rollback()
            eliminar_pdf(pdf_filename)
            flash("Este correo electrónico ya está registrado.", "error")

        finally:
            conn.close()

    return render_template("registro.html")


# ==========================================================
# 9. CERRAR SESIÓN
# ==========================================================

@app.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión correctamente.", "info")
    return redirect(url_for("login"))


# ==========================================================
# 10. CONSULTAR Y FILTRAR EMPLEOS
# ==========================================================

@app.route("/empleos")
@login_requerido
def ver_empleos():
    usuaria = obtener_usuaria_actual()

    if not usuaria:
        session.clear()
        return redirect(url_for("login"))

    sector_filtro = request.args.get(
        "sector", "Todos los sectores"
    )

    jornada_filtro = request.args.get(
        "jornada", "Todas las jornadas"
    )

    ubicacion_filtro = request.args.get(
        "ubicacion", "Todas las ubicaciones"
    )

    consulta = """
        SELECT * FROM vacantes
        WHERE activa = 1
    """

    parametros = []

    if sector_filtro != "Todos los sectores":
        consulta += " AND sector = ?"
        parametros.append(sector_filtro)

    if jornada_filtro != "Todas las jornadas":
        consulta += " AND jornada = ?"
        parametros.append(jornada_filtro)

    if ubicacion_filtro != "Todas las ubicaciones":
        consulta += " AND ubicacion = ?"
        parametros.append(ubicacion_filtro)

    consulta += " ORDER BY id DESC"

    conn = get_db_connection()

    vacantes = conn.execute(
        consulta,
        parametros
    ).fetchall()

    postulaciones = conn.execute("""
        SELECT vacante_id
        FROM postulaciones
        WHERE usuaria_id = ?
    """, (usuaria["id"],)).fetchall()

    ids_postuladas = [
        p["vacante_id"] for p in postulaciones
    ]

    conn.close()

    return render_template(
        "empleos.html",
        usuaria=usuaria,
        vacantes=vacantes,
        ids_postuladas=ids_postuladas,
        sectores=SECTORES,
        jornadas=JORNADAS,
        ubicaciones=UBICACIONES,
        sector_sel=sector_filtro,
        jornada_sel=jornada_filtro,
        ubicacion_sel=ubicacion_filtro
    )


# ==========================================================
# 11. POSTULARSE A UNA VACANTE
# ==========================================================

@app.route("/postular/<int:id_vacante>", methods=["POST"])
@login_requerido
def postular(id_vacante):
    usuaria = obtener_usuaria_actual()

    if not usuaria:
        return redirect(url_for("login"))

    if usuaria["estado"] != "Validada":
        flash(
            "Tu cuenta debe ser validada por el administrador antes de postularte.",
            "error"
        )
        return redirect(url_for("ver_empleos"))

    conn = get_db_connection()

    vacante = conn.execute("""
        SELECT id FROM vacantes
        WHERE id = ? AND activa = 1
    """, (id_vacante,)).fetchone()

    if not vacante:
        conn.close()
        flash("La vacante ya no está disponible.", "error")
        return redirect(url_for("ver_empleos"))

    existente = conn.execute("""
        SELECT id FROM postulaciones
        WHERE usuaria_id = ? AND vacante_id = ?
    """, (usuaria["id"], id_vacante)).fetchone()

    if existente:
        flash("Ya te has postulado a esta vacante.", "info")
    else:
        conn.execute("""
            INSERT INTO postulaciones
            (usuaria_id, vacante_id, estado)
            VALUES (?, ?, 'Enviada')
        """, (usuaria["id"], id_vacante))

        conn.commit()
        flash("¡Tu postulación se registró correctamente!", "success")

    conn.close()

    return redirect(url_for("ver_empleos"))


# ==========================================================
# 12. CAPACITACIONES
# ==========================================================

@app.route("/capacitaciones")
@login_requerido
def capacitaciones():
    usuaria = obtener_usuaria_actual()

    conn = get_db_connection()

    cursos = conn.execute("""
        SELECT
            c.*,
            CASE
                WHEN i.id IS NOT NULL THEN 1
                ELSE 0
            END AS inscrita
        FROM capacitaciones c
        LEFT JOIN inscripciones i
            ON i.curso_id = c.id
            AND i.usuaria_id = ?
        WHERE c.activa = 1
        ORDER BY c.id
    """, (usuaria["id"],)).fetchall()

    conn.close()

    return render_template(
        "capacitaciones.html",
        usuaria=usuaria,
        cursos=cursos
    )


# ==========================================================
# 13. INSCRIPCIÓN A CAPACITACIONES
# ==========================================================

@app.route("/inscribirse/<int:id_curso>", methods=["POST"])
@login_requerido
def inscribirse(id_curso):
    usuaria = obtener_usuaria_actual()

    conn = get_db_connection()

    curso = conn.execute("""
        SELECT id FROM capacitaciones
        WHERE id = ? AND activa = 1
    """, (id_curso,)).fetchone()

    if not curso:
        conn.close()
        flash("El curso no está disponible.", "error")
        return redirect(url_for("capacitaciones"))

    try:
        conn.execute("""
            INSERT INTO inscripciones
            (usuaria_id, curso_id)
            VALUES (?, ?)
        """, (usuaria["id"], id_curso))

        conn.commit()
        flash("¡Te has inscrito correctamente al curso!", "success")

    except sqlite3.IntegrityError:
        flash("Ya estás inscrita en este curso.", "info")

    finally:
        conn.close()

    return redirect(url_for("capacitaciones"))


# ==========================================================
# 14. PERFIL Y POSTULACIONES DE LA USUARIA
# ==========================================================

@app.route("/perfil")
@login_requerido
def mi_perfil():
    usuaria = obtener_usuaria_actual()

    conn = get_db_connection()

    postulaciones_db = conn.execute("""
        SELECT
            p.id,
            p.fecha,
            p.estado,
            v.id AS vacante_id,
            v.titulo,
            v.empresa,
            v.salario
        FROM postulaciones p
        INNER JOIN vacantes v ON v.id = p.vacante_id
        WHERE p.usuaria_id = ?
        ORDER BY p.fecha DESC
    """, (usuaria["id"],)).fetchall()

    mis_postulaciones = []

    for p in postulaciones_db:
        mis_postulaciones.append({
            "id": p["id"],
            "fecha": p["fecha"],
            "estado": p["estado"],
            "vacante": {
                "id": p["vacante_id"],
                "titulo": p["titulo"],
                "empresa": p["empresa"],
                "salario": p["salario"]
            }
        })

    mis_cursos = conn.execute("""
        SELECT
            i.fecha,
            i.estado,
            c.titulo,
            c.duracion,
            c.modalidad
        FROM inscripciones i
        INNER JOIN capacitaciones c ON c.id = i.curso_id
        WHERE i.usuaria_id = ?
        ORDER BY i.fecha DESC
    """, (usuaria["id"],)).fetchall()

    conn.close()

    return render_template(
        "perfil.html",
        usuaria=usuaria,
        postulaciones=mis_postulaciones,
        mis_cursos=mis_cursos
    )


# ==========================================================
# 15. PANEL DE ADMINISTRACIÓN
# ==========================================================

@app.route("/admin")
@admin_requerido
def panel_admin():
    conn = get_db_connection()

    usuarias = conn.execute("""
        SELECT
            u.*,
            COUNT(p.id) AS total_postulaciones
        FROM usuarias u
        LEFT JOIN postulaciones p ON p.usuaria_id = u.id
        WHERE u.correo != 'admin@redvaliente.org'
        GROUP BY u.id
        ORDER BY u.id DESC
    """).fetchall()

    total_vacantes = conn.execute("""
        SELECT COUNT(*) AS total
        FROM vacantes
        WHERE activa = 1
    """).fetchone()["total"]

    total_postulaciones = conn.execute("""
        SELECT COUNT(*) AS total
        FROM postulaciones
    """).fetchone()["total"]

    total_inscripciones = conn.execute("""
        SELECT COUNT(*) AS total
        FROM inscripciones
    """).fetchone()["total"]

    vacantes = conn.execute("""
        SELECT * FROM vacantes
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        usuarias=usuarias,
        vacantes=vacantes,
        total_vacantes=total_vacantes,
        total_postulaciones=total_postulaciones,
        total_inscripciones=total_inscripciones
    )


# ==========================================================
# 16. APROBAR USUARIA
# ==========================================================

@app.route("/aprobar/<int:id_usr>", methods=["POST"])
@admin_requerido
def aprobar(id_usr):
    conn = get_db_connection()

    conn.execute("""
        UPDATE usuarias
        SET estado = 'Validada'
        WHERE id = ?
        AND correo != 'admin@redvaliente.org'
    """, (id_usr,))

    conn.commit()
    conn.close()

    flash("La cuenta fue aprobada correctamente.", "success")

    return redirect(url_for("panel_admin"))


# ==========================================================
# 17. RECHAZAR USUARIA
# ==========================================================

@app.route("/rechazar/<int:id_usr>", methods=["POST"])
@admin_requerido
def rechazar(id_usr):
    conn = get_db_connection()

    conn.execute("""
        UPDATE usuarias
        SET estado = 'Rechazada'
        WHERE id = ?
        AND correo != 'admin@redvaliente.org'
    """, (id_usr,))

    conn.commit()
    conn.close()

    flash("La cuenta fue rechazada.", "info")

    return redirect(url_for("panel_admin"))


# ==========================================================
# 18. ELIMINAR USUARIA
# ==========================================================

@app.route("/eliminar_usuaria/<int:id_usr>", methods=["POST"])
@admin_requerido
def eliminar_usuaria(id_usr):
    conn = get_db_connection()

    usuaria = conn.execute("""
        SELECT pdf_soporte
        FROM usuarias
        WHERE id = ?
        AND correo != 'admin@redvaliente.org'
    """, (id_usr,)).fetchone()

    if not usuaria:
        conn.close()
        flash("No se encontró la usuaria.", "error")
        return redirect(url_for("panel_admin"))

    conn.execute(
        "DELETE FROM postulaciones WHERE usuaria_id = ?",
        (id_usr,)
    )

    conn.execute(
        "DELETE FROM inscripciones WHERE usuaria_id = ?",
        (id_usr,)
    )

    conn.execute(
        "DELETE FROM usuarias WHERE id = ?",
        (id_usr,)
    )

    conn.commit()
    conn.close()

    eliminar_pdf(usuaria["pdf_soporte"])

    flash("La usuaria fue eliminada correctamente.", "success")

    return redirect(url_for("panel_admin"))


# ==========================================================
# 19. CREAR VACANTE
# ==========================================================

@app.route("/admin/vacantes/crear", methods=["GET", "POST"])
@admin_requerido
def crear_vacante():
    if request.method == "POST":
        datos = {
            "titulo": request.form.get("titulo", "").strip(),
            "empresa": request.form.get("empresa", "").strip(),
            "salario": request.form.get("salario", "").strip(),
            "jornada": request.form.get("jornada", "").strip(),
            "sector": request.form.get("sector", "").strip(),
            "ubicacion": request.form.get("ubicacion", "").strip(),
            "descripcion": request.form.get("descripcion", "").strip()
        }

        error = validar_datos_vacante(datos)

        if error:
            flash(error, "error")
            return render_template(
                "vacante_formulario.html",
                vacante=datos,
                accion="Crear"
            )

        conn = get_db_connection()

        conn.execute("""
            INSERT INTO vacantes
            (titulo, empresa, salario, jornada, sector,
             ubicacion, descripcion, activa)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            datos["titulo"],
            datos["empresa"],
            datos["salario"],
            datos["jornada"],
            datos["sector"],
            datos["ubicacion"],
            datos["descripcion"]
        ))

        conn.commit()
        conn.close()

        flash("La vacante fue creada correctamente.", "success")

        return redirect(url_for("panel_admin"))

    return render_template(
        "vacante_formulario.html",
        vacante=None,
        accion="Crear"
    )


# ==========================================================
# 20. EDITAR VACANTE
# ==========================================================

@app.route(
    "/admin/vacantes/editar/<int:id_vacante>",
    methods=["GET", "POST"]
)
@admin_requerido
def editar_vacante(id_vacante):
    conn = get_db_connection()

    vacante = conn.execute("""
        SELECT * FROM vacantes
        WHERE id = ?
    """, (id_vacante,)).fetchone()

    if not vacante:
        conn.close()
        abort(404)

    if request.method == "POST":
        datos = {
            "titulo": request.form.get("titulo", "").strip(),
            "empresa": request.form.get("empresa", "").strip(),
            "salario": request.form.get("salario", "").strip(),
            "jornada": request.form.get("jornada", "").strip(),
            "sector": request.form.get("sector", "").strip(),
            "ubicacion": request.form.get("ubicacion", "").strip(),
            "descripcion": request.form.get("descripcion", "").strip()
        }

        error = validar_datos_vacante(datos)

        if error:
            conn.close()
            flash(error, "error")

            return render_template(
                "vacante_formulario.html",
                vacante=datos,
                accion="Editar"
            )

        conn.execute("""
            UPDATE vacantes
            SET titulo = ?,
                empresa = ?,
                salario = ?,
                jornada = ?,
                sector = ?,
                ubicacion = ?,
                descripcion = ?
            WHERE id = ?
        """, (
            datos["titulo"],
            datos["empresa"],
            datos["salario"],
            datos["jornada"],
            datos["sector"],
            datos["ubicacion"],
            datos["descripcion"],
            id_vacante
        ))

        conn.commit()
        conn.close()

        flash("La vacante fue actualizada correctamente.", "success")

        return redirect(url_for("panel_admin"))

    conn.close()

    return render_template(
        "vacante_formulario.html",
        vacante=vacante,
        accion="Editar"
    )


# ==========================================================
# 21. DESACTIVAR VACANTE
# ==========================================================

@app.route(
    "/admin/vacantes/eliminar/<int:id_vacante>",
    methods=["POST"]
)
@admin_requerido
def eliminar_vacante(id_vacante):
    conn = get_db_connection()

    conn.execute("""
        UPDATE vacantes
        SET activa = 0
        WHERE id = ?
    """, (id_vacante,))

    conn.commit()
    conn.close()

    flash("La vacante fue desactivada.", "success")

    return redirect(url_for("panel_admin"))


# ==========================================================
# 22. EJECUTAR APLICACIÓN
# ==========================================================

if __name__ == "__main__":
    app.run(debug=True)