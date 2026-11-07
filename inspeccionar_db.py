import sqlite3

conexion = sqlite3.connect("red_valiente.db")

for tabla in ["usuarias", "vacantes", "postulaciones"]:
    print("\n" + "=" * 50)
    print("TABLA:", tabla)
    print("=" * 50)

    columnas = conexion.execute(
        f'PRAGMA table_info("{tabla}")'
    ).fetchall()

    for columna in columnas:
        print(
            f"Nombre: {columna[1]} | "
            f"Tipo: {columna[2]} | "
            f"Obligatorio: {bool(columna[3])} | "
            f"Valor predeterminado: {columna[4]} | "
            f"Clave primaria: {bool(columna[5])}"
        )

    print("\nClaves foráneas:")
    for clave in conexion.execute(
        f'PRAGMA foreign_key_list("{tabla}")'
    ).fetchall():
        print(clave)

conexion.close()
