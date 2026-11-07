import sqlite3

conn = sqlite3.connect("red_valiente.db")
conn.row_factory = sqlite3.Row

for tabla in ["usuarias", "vacantes", "postulaciones"]:
    print(f"\n========== {tabla.upper()} ==========")
    filas = conn.execute(f"SELECT * FROM {tabla}").fetchall()

    for fila in filas:
        datos = dict(fila)

        # No mostrar contraseñas ni sus hashes
        if tabla == "usuarias":
            datos.pop("clave", None)

        print(datos)

conn.close()
