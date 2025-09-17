import os
import re
from pathlib import Path

# --- CONFIGURACION POR DEFECTO ---
# Patrones comunes para ignorar si no se encuentra un archivo .gitignore
DEFAULT_IGNORE_PATTERNS = [
    '__pycache__',
    '.venv',
    '.env',
    '*.log',
    'dist',
    'build',
    '*.pyc',
    '*.exe',
    '*.sqlite3',
    '*.db',
    '*.iml',
    '*.swp',
    '*.swo'
]

# Archivos y directorios que siempre se ignoran sin importar el .gitignore
HARDCODED_IGNORE_PATTERNS = [
    '.git', # Carpeta de Git
    '.svn', # Carpeta de Subversion
    '.hg',  # Carpeta de Mercurial
    '.gitignore', # El propio archivo .gitignore
    'README.md' # Archivo README.md
]

def get_gitignore_patterns(folder_path):
    """
    Lee y procesa los patrones de un archivo .gitignore en la carpeta.
    Si no existe, devuelve los patrones por defecto.
    """
    gitignore_path = Path(folder_path) / '.gitignore'
    patterns = []
    
    if gitignore_path.is_file():
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Ignorar comentarios y lineas vacias
                    if line and not line.startswith('#'):
                        patterns.append(line)
        except Exception as e:
            print(f"Advertencia: No se pudo leer el archivo .gitignore. Usando patrones por defecto. Detalle: {e}")
            return DEFAULT_IGNORE_PATTERNS
    else:
        print("Archivo .gitignore no encontrado. Usando patrones por defecto.")
        return DEFAULT_IGNORE_PATTERNS
    
    return patterns

def should_ignore(path, patterns):
    """
    Verifica si un path debe ser ignorado segun los patrones.
    
    La logica maneja tanto las reglas de inclusion ('!') como de exclusion.
    """
    # Usar el metodo match de Path para manejar comodines y reglas de inclusion
    for pattern in patterns:
        if pattern.startswith('!'):
            if path.match(pattern[1:].strip()):
                return False  # Coincide con una excepcion, no ignorar
    
    for pattern in patterns:
        if not pattern.startswith('!'):
            if path.match(pattern):
                return True  # Coincide con una regla de exclusion, ignorar
    
    return False

def generate_file_structure(startpath, ignore_patterns):
    """
    Crea una cadena de texto que representa la estructura de archivos y carpetas.
    """
    lines = []
    for root, dirs, files in os.walk(startpath, topdown=True):
        
        # Filtrar directorios a ignorar ANTES de continuar
        dirs[:] = [d for d in dirs if not should_ignore(Path(root) / d, ignore_patterns)]

        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        
        # Anadir la carpeta actual al arbol
        if root != startpath:
            lines.append(f"{indent}|--{os.path.basename(root)}/")

        subindent = ' ' * 4 * (level + 1)
        for f in files:
            file_path = Path(root) / f
            if not should_ignore(file_path, ignore_patterns):
                lines.append(f"{subindent}|--{f}")
                
    return "\n".join(lines)


def organizar_carpeta(carpeta_raiz, script_filename):
    """
    Escanea la carpeta raiz, primero genera una estructura, luego concatena el contenido de los archivos.
    """
    if not os.path.isdir(carpeta_raiz):
        return f"Error: La carpeta '{carpeta_raiz}' no existe."

    # Obtener los patrones de .gitignore
    gitignore_patterns = get_gitignore_patterns(carpeta_raiz)
    
    # Combinar todos los patrones de exclusion, incluyendo el propio script
    all_ignore_patterns = gitignore_patterns + HARDCODED_IGNORE_PATTERNS + [script_filename]

    contenido_final = []
    seccion_actual = os.path.basename(carpeta_raiz)
    
    # --- PARTE 1: ESTRUCTURA DE ARCHIVOS ---
    contenido_final.append(f"{seccion_actual.capitalize()}" + "+" * 35 + "\n")
    contenido_final.append("Estructura de Archivos" + "-" * 23 + "\n")
    contenido_final.append(generate_file_structure(carpeta_raiz, all_ignore_patterns) + "\n\n")

    # --- PARTE 2: CONTENIDO DE LOS ARCHIVOS ---
    contenido_final.append("Contenido de Archivos" + "-" * 23 + "\n\n")

    for dirpath, dirnames, filenames in os.walk(carpeta_raiz):
        
        # Filtrar directorios a ignorar ANTES de continuar
        dirnames[:] = [d for d in dirnames if not should_ignore(Path(dirpath) / d, all_ignore_patterns)]

        for filename in filenames:
            file_path = Path(dirpath) / filename
            
            # Verificar si el archivo debe ser ignorado
            if not should_ignore(file_path, all_ignore_patterns):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        contenido = f.read()
                except UnicodeDecodeError:
                    # Si falla, intenta con una codificacion mas flexible como 'latin-1'
                    try:
                        with open(file_path, 'r', encoding='latin-1') as f:
                            contenido = f.read()
                    except Exception as e:
                        print(f"Advertencia: No se pudo leer el archivo {file_path} por un error de codificacion. Detalle: {e}")
                        continue # Salta este archivo
                except Exception as e:
                    # Para otros errores de lectura
                    print(f"Advertencia: No se pudo leer el archivo {file_path}. Detalle: {e}")
                    continue

                relative_path = os.path.relpath(file_path, carpeta_raiz)
                
                contenido_final.append(f"{relative_path}" + "-" * 40 + "\n")
                contenido_final.append(contenido + "\n")

    return "".join(contenido_final)

if __name__ == "__main__":
    
    directorio_actual = os.getcwd()
    script_filename = os.path.basename(__file__)

    print("--- Organizar Codigo ---")
    print(f"El directorio actual es: {directorio_actual}")
    input_path = input("Ingresa la ruta de la carpeta a escanear (deja en blanco para usar el directorio actual): ")

    if not input_path:
        input_path = directorio_actual

    contenido_unido = organizar_carpeta(input_path, script_filename)
    
    # Imprimir el resultado
    print("\n" + "="*50 + "\n")
    print(contenido_unido)
    print("\n" + "="*50 + "\n")

    # Ofrecer guardar el resultado en un archivo
    guardar_en_archivo = input("Deseas guardar este contenido en un archivo? (s/n): ")
    if guardar_en_archivo.lower() == 's':
        nombre_archivo_salida = input("Ingresa el nombre del archivo de salida (ej. codigo_unido.txt): ")
        if nombre_archivo_salida:
            try:
                with open(nombre_archivo_salida, 'w', encoding='utf-8') as f:
                    f.write(contenido_unido)
                print(f"Contenido guardado exitosamente en '{nombre_archivo_salida}'")
            except Exception as e:
                print(f"Error al guardar el archivo: {e}")
