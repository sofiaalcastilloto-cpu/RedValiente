import os
import sqlite3
import hashlib
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "red_valiente_secret_key"

# --- 1. CONFIGURACIÓN CARGA DE ARCHIVOS PDF ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- 2. BASE DE DATOS SQLITE ---
def get_db_connection():
    conn = sqlite3.connect('red_valiente.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # Crear tabla usuarias
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT UNIQUE NOT NULL,
            telefono TEXT NOT NULL,
            clave TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Pendiente',
            pdf_soporte TEXT
        )
    ''')
    
    # Crear tabla postulaciones
    conn.execute('''
        CREATE TABLE IF NOT EXISTS postulaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuaria_id INTEGER NOT NULL,
            vacante_id INTEGER NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuaria_id) REFERENCES usuarias (id)
        )
    ''')
    
    # Insertar al Administrador por defecto si no existe
    admin = conn.execute("SELECT * FROM usuarias WHERE correo='admin@redvaliente.org'").fetchone()
    if not admin:
        clave_admin = hashlib.sha256("admin123".encode()).hexdigest()
        conn.execute("INSERT INTO usuarias (nombre, correo, telefono, clave, estado) VALUES (?, ?, ?, ?, ?)",
                     ("Admin", "admin@redvaliente.org", "0000", clave_admin, "Validada"))

    conn.commit()
    conn.close()

init_db()

# --- 3. AMPLIACIÓN DE VACANTES Y SECTORES ---
class Vacante:
    def __init__(self, id_vacante, titulo, empresa, salario, jornada, sector, ubicacion, descripcion):
        self.id = id_vacante
        self.titulo = titulo
        self.empresa = empresa
        self.salario = salario
        self.jornada = jornada
        self.sector = sector
        self.ubicacion = ubicacion
        self.descripcion = descripcion

vacantes_lista = [
    Vacante(1, "Auxiliar de Enfermería", "Clínica San José", "$1'800.000", "Tiempo Completo", "Salud", "Bogotá", "Apoyo en atención a pacientes y gestión de historias clínicas."),
    Vacante(2, "Desarrolladora Junior", "Tech Solutions", "$2'500.000", "Tiempo Completo", "Tecnología", "Medellín", "Desarrollo y mantenimiento de aplicaciones web en Python y JavaScript."),
    Vacante(3, "Atención al Cliente", "Teleperformance", "$1'500.000", "Horario Flexible", "Atención al Cliente", "Bogotá", "Gestión de soporte y canales de comunicación telefónicos y digitales."),
    Vacante(4, "Auxiliar de Cocina y Pastelería", "Restaurante El Sazón", "$1'400.000", "Tiempo Completo", "Gastronomía", "Bogotá", "Preparación de ingredientes, apoyo al chef y empaque de pedidos."),
    Vacante(5, "Operario de Servicios Generales", "Limpio & Seguro Co.", "$1'300.000", "Horario Flexible", "Servicios Generales", "Medellín", "Mantenimiento y desinfección de áreas comerciales e industriales."),
    Vacante(6, "Asistente Administrativa", "Grupo Financiero Alfa", "$2'000.000", "Tiempo Completo", "Administrativo", "Bogotá", "Organización de agenda, manejo de correspondencia y recepción."),
    Vacante(7, "Tutora de Apoyo Escolar", "Fundación Educar", "$1'600.000", "Medio Tiempo", "Educación", "Remoto", "Acompañamiento a niños y jóvenes en tareas escolares y refuerzo académico."),
    Vacante(8, "Coordinadora de Logística e Inventarios", "Bodegas del Norte", "$2'200.000", "Tiempo Completo", "Logística", "Bogotá", "Control de entradas, salidas y organización de stock en almacén.")
]

# LISTA COMPLETA DE SECTORES PARA LOS FILTROS
SECTORES = ["Todos los sectores", "Salud", "Tecnología", "Atención al Cliente", "Gastronomía", "Servicios Generales", "Administrativo", "Educación", "Logística"]
JORNADAS = ["Todas las jornadas", "Tiempo Completo", "Medio Tiempo", "Horario Flexible"]
UBICACIONES = ["Todas las ubicaciones", "Bogotá", "Medellín", "Remoto"]

# --- 4. RUTAS DEL SISTEMA ---
@app.route("/")
@app.route("/inicio")
def inicio():
    if "usuario" in session:
        return redirect(url_for("ver_empleos"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form.get("correo")
        clave = request.form.get("clave")
        clave_encriptada = hashlib.sha256(clave.encode()).hexdigest()
        
        conn = get_db_connection()
        usuaria = conn.execute('SELECT * FROM usuarias WHERE correo = ? AND clave = ?', (correo, clave_encriptada)).fetchone()
        conn.close()
        
        if usuaria:
            session["usuario"] = usuaria["correo"]
            session["nombre"] = usuaria["nombre"]
            session["rol"] = "admin" if usuaria["correo"] == "admin@redvaliente.org" else "usuaria"
            if usuaria["correo"] == "admin@redvaliente.org":
                return redirect(url_for("panel_admin"))
            else:
                return redirect(url_for("ver_empleos"))
        else:
            flash("Correo o contraseña incorrectos.", "error")
            
    return render_template("login.html")

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        correo = request.form.get("correo")
        telefono = request.form.get("telefono")
        clave = request.form.get("clave")
        clave_encriptada = hashlib.sha256(clave.encode()).hexdigest()
        
        pdf_file = request.files.get("pdf_soporte")
        pdf_filename = None
        if pdf_file and pdf_file.filename.endswith('.pdf'):
            filename_seguro = secure_filename(pdf_file.filename)
            pdf_filename = f"{uuid.uuid4()}_{filename_seguro}"
            pdf_file.save(os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename))

        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO usuarias (nombre, correo, telefono, clave, pdf_soporte) VALUES (?, ?, ?, ?, ?)',
                         (nombre, correo, telefono, clave_encriptada, pdf_filename))
            conn.commit()
            flash("¡Registro exitoso! Por favor inicia sesión.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("El correo electrónico ya se encuentra registrado.", "error")
        finally:
            conn.close()

    return render_template("registro.html")

@app.route("/empleos")
def ver_empleos():
    if "usuario" not in session:
        return redirect(url_for("login"))
    
    # Parámetros de filtrado
    sector_filtro = request.args.get("sector", "Todos los sectores")
    jornada_filtro = request.args.get("jornada", "Todas las jornadas")
    ubicacion_filtro = request.args.get("ubicacion", "Todas las ubicaciones")

    # Filtrar la lista de vacantes
    vacantes_filtradas = vacantes_lista
    if sector_filtro != "Todos los sectores":
        vacantes_filtradas = [v for v in vacantes_filtradas if v.sector == sector_filtro]
    if jornada_filtro != "Todas las jornadas":
        vacantes_filtradas = [v for v in vacantes_filtradas if v.jornada == jornada_filtro]
    if ubicacion_filtro != "Todas las ubicaciones":
        vacantes_filtradas = [v for v in vacantes_filtradas if v.ubicacion == ubicacion_filtro]
    
    conn = get_db_connection()
    usuaria_actual = conn.execute('SELECT * FROM usuarias WHERE correo = ?', (session["usuario"],)).fetchone()
    
    postulaciones = conn.execute('SELECT vacante_id FROM postulaciones WHERE usuaria_id = ?', (usuaria_actual["id"],)).fetchall()
    ids_postuladas = [p["vacante_id"] for p in postulaciones]
    
    conn.close()
    
    return render_template(
        "empleos.html", 
        vacantes=vacantes_filtradas, 
        usuaria=usuaria_actual, 
        ids_postuladas=ids_postuladas,
        sectores=SECTORES,
        jornadas=JORNADAS,
        ubicaciones=UBICACIONES,
        sector_sel=sector_filtro,
        jornada_sel=jornada_filtro,
        ubicacion_sel=ubicacion_filtro
    )

@app.route("/postular/<int:id_vacante>", methods=["POST"])
def postular(id_vacante):
    if "usuario" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    usuaria_actual = conn.execute('SELECT * FROM usuarias WHERE correo = ?', (session["usuario"],)).fetchone()
    
    if usuaria_actual["estado"] != "Validada":
        flash("Tu cuenta debe estar validada por el administrador para postularte a empleos.", "error")
        conn.close()
        return redirect(url_for("ver_empleos"))
        
    existente = conn.execute('SELECT * FROM postulaciones WHERE usuaria_id = ? AND vacante_id = ?', 
                             (usuaria_actual["id"], id_vacante)).fetchone()
    if not existente:
        conn.execute('INSERT INTO postulaciones (usuaria_id, vacante_id) VALUES (?, ?)', (usuaria_actual["id"], id_vacante))
        conn.commit()
        flash("¡Postulación realizada con éxito!", "success")
    else:
        flash("Ya te encuentras postulada a esta vacante.", "info")
        
    conn.close()
    return redirect(url_for("ver_empleos"))

@app.route("/capacitaciones")
def capacitaciones():
    if "usuario" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    usuaria_actual = conn.execute('SELECT * FROM usuarias WHERE correo = ?', (session["usuario"],)).fetchone()
    conn.close()
    
    cursos = [
        {"id": 1, "titulo": "Habilidades Digitales y Ofimática", "duracion": "40 Horas", "modalidad": "Virtual", "categoria": "Tecnología"},
        {"id": 2, "titulo": "Emprendimiento y Finanzas Personales", "duracion": "30 Horas", "modalidad": "Presencial / Virtual", "categoria": "Negocios"},
        {"id": 3, "titulo": "Excel Profesional para Gestión Administrativa", "duracion": "25 Horas", "modalidad": "Virtual", "categoria": "Herramientas"},
        {"id": 4, "titulo": "Servicio al Cliente y Comunicación Asertiva", "duracion": "20 Horas", "modalidad": "Virtual", "categoria": "Servicios"}
    ]
    return render_template("capacitaciones.html", usuaria=usuaria_actual, cursos=cursos)

@app.route("/perfil")
def mi_perfil():
    if "usuario" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    usuaria_actual = conn.execute('SELECT * FROM usuarias WHERE correo = ?', (session["usuario"],)).fetchone()
    
    # Obtener vacantes a las que se ha postulado
    postulaciones_db = conn.execute('''
        SELECT p.fecha, p.vacante_id 
        FROM postulaciones p 
        WHERE p.usuaria_id = ?
    ''', (usuaria_actual["id"],)).fetchall()
    
    mis_postulaciones = []
    for p in postulaciones_db:
        vacante_obj = next((v for v in vacantes_lista if v.id == p["vacante_id"]), None)
        if vacante_obj:
            mis_postulaciones.append({
                "vacante": vacante_obj,
                "fecha": p["fecha"]
            })
            
    conn.close()
    return render_template("perfil.html", usuaria=usuaria_actual, postulaciones=mis_postulaciones)

@app.route("/admin")
def panel_admin():
    if session.get("usuario") != "admin@redvaliente.org":
        flash("Acceso denegado. Se requieren permisos de administrador.", "error")
        return redirect(url_for("ver_empleos"))
        
    conn = get_db_connection()
    todas_las_usuarias = conn.execute('''
        SELECT u.*, COUNT(p.id) as total_postulaciones 
        FROM usuarias u 
        LEFT JOIN postulaciones p ON u.id = p.usuaria_id 
        WHERE u.correo != "admin@redvaliente.org"
        GROUP BY u.id
    ''').fetchall()
    conn.close()
    
    return render_template("admin.html", usuarias=todas_las_usuarias, total_vacantes=len(vacantes_lista))

@app.route("/aprobar/<int:id_usr>")
def aprobar(id_usr):
    if session.get("usuario") != "admin@redvaliente.org":
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    conn.execute('UPDATE usuarias SET estado = "Validada" WHERE id = ?', (id_usr,))
    conn.commit()
    conn.close()
    flash("Usuaria aprobada correctamente.", "success")
    return redirect(url_for("panel_admin"))

@app.route("/eliminar_usuaria/<int:id_usr>")
def eliminar_usuaria(id_usr):
    if session.get("usuario") != "admin@redvaliente.org":
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    usr = conn.execute('SELECT pdf_soporte FROM usuarias WHERE id = ?', (id_usr,)).fetchone()
    if usr and usr["pdf_soporte"]:
        ruta_pdf = os.path.join(app.config['UPLOAD_FOLDER'], usr["pdf_soporte"])
        if os.path.exists(ruta_pdf):
            os.remove(ruta_pdf)
            
    conn.execute('DELETE FROM postulaciones WHERE usuaria_id = ?', (id_usr,))
    conn.execute('DELETE FROM usuarias WHERE id = ?', (id_usr,))
    conn.commit()
    conn.close()
    flash("Usuaria eliminada correctamente.", "success")
    return redirect(url_for("panel_admin"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión exitosamente.", "info")
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)