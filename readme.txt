================================================================================
GUIA DE CONFIGURACION Y EJECUCION LOCAL (VS CODE)
Pipeline de Procesamiento, Limpieza y Prediccion de Matricula (2007-2026)
================================================================================

NOTA IMPORTANTE SOBRE EL ENTORNO DE EJECUCION
--------------------------------------------------------------------------------
Este manual de instalacion y configuracion esta diseñado EXCLUSIVAMENTE para 
ejecutar el proyecto de forma local dentro de Visual Studio Code (VS Code).

Razon del uso de VS Code local:
El motivo principal para trabajar de forma local en VS Code en lugar de utilizar
plataformas en la nube como Google Colab fue la restriccion de espacio de 
almacenamiento en Google Drive. El volumen total de los datasets de matricula 
historica (archivos CSV desde el ano 2007 hasta 2025) superaba la capacidad 
disponible en la cuenta de Drive, por lo que se opto por procesar todo el 
pipeline en el disco duro del equipo local, donde se dispone de mayor espacio.

Diferencia con Google Colab:
Si este codigo se ejecutara en Google Colab, no seria necesario realizar la 
creacion de entornos virtuales (venv), ni configurar interpretes o instalar 
manualmente la mayoria de las librerias, ya que Colab incluye este entorno 
preconfigurado y bastaria con subir el script y ejecutar las celdas directamente.


1. REQUISITOS DEL SISTEMA
--------------------------------------------------------------------------------
- Python: Version 3.10 o superior (Recomendado 3.10.x o 3.11.x).
- Editor: Visual Studio Code.
- Sistema Operativo: Windows, macOS o Linux.


2. EXTENSIONES RECOMENDADAS PARA VS CODE
--------------------------------------------------------------------------------
Para facilitar la ejecucion, depuracion y visualizacion de los datos en VS Code, 
se recomienda instalar las siguientes extensiones desde el panel lateral 
(Ctrl + Shift + X):

- Python (ms-python.python): Soporte basico de Python, autocompletado y depuracion.
- Pylance (ms-python.vscode-pylance): Analisis estatico de codigo de alto rendimiento.
- Jupyter (ms-toolsai.jupyter): Permite ejecutar celdas de codigo interactivo (# %%).
- vscode-parquet (dvne.vscode-parquet-viewer): Permite abrir y revisar archivos .parquet directamente en VS Code.
- Excel Viewer (GrapeCity.gc-excelviewer): Permite visualizar la matriz carreras_agrupadas.xlsx.


3. CONFIGURACION DEL ENTORNO VIRTUAL (VENV)
--------------------------------------------------------------------------------
Paso 3.1: Abrir la carpeta del proyecto en VS Code
Abra VS Code y seleccione Archivo > Abrir carpeta..., seleccionando el directorio 
raiz del proyecto.

Paso 3.2: Crear el entorno virtual desde la terminal integrada (Ctrl + ~)
En Windows:
python -m venv venv

En Linux / macOS:
python3 -m venv venv

Paso 3.3: Activar el entorno virtual
En Windows (PowerShell):
.\venv\Scripts\Activate.ps1
(Si existe restriccion de ejecucion, ejecutar previamente: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process)

En Windows (CMD):
venv\Scripts\activate.bat

En Linux / macOS:
source venv/bin/activate

Paso 3.4: Seleccionar el interprete en VS Code
1. Presione Ctrl + Shift + P (o Cmd + Shift + P en Mac).
2. Busque "Python: Select Interpreter" (Python: Seleccionar interprete).
3. Seleccione la ruta correspondiente al entorno virtual creado (./venv/Scripts/python.exe).


4. INSTALACION DE LIBRERIAS Y DEPENDENCIAS
--------------------------------------------------------------------------------
Con el entorno virtual activo, actualice el gestor de paquetes e instale todas 
las librerias requeridas ejecutando:

python -m pip install --upgrade pip
pip install pandas pyarrow openpyxl numpy duckdb matplotlib seaborn scikit-learn xgboost lightgbm

Opcionalmente, puede crear un archivo llamado "requirements.txt" con el siguiente contenido:

pandas>=2.0.0
pyarrow>=12.0.0
openpyxl>=3.1.0
numpy>=1.24.0
duckdb>=0.8.0
matplotlib>=3.7.0
seaborn>=0.12.0
scikit-learn>=1.2.0
xgboost>=1.7.0
lightgbm>=3.3.0

E instalarlo ejecutando:
pip install -r requirements.txt


5. DESGLOSE DE BIBLIOTECAS UTILIZADAS
--------------------------------------------------------------------------------
- pandas: Carga, filtrado, agrupamiento y transformacion de estructuras de datos.
- pyarrow: Motor de lectura y escritura para archivos comprimidos Parquet.
- openpyxl: Lectura de archivos de hojas de calculo Excel (.xlsx).
- numpy: Operaciones matriciales, calculo de retardos temporales y metricas.
- duckdb: Motor SQL de alto rendimiento para consultas directas sobre Parquet.
- matplotlib: Generacion del lienzo de visualizacion y tablero grafico.
- seaborn: Estilizacion de graficos estadisticos e histogramas.
- scikit-learn: Evaluacion de modelos, metricas (MAE, RMSE, R2) y Random Forest.
- xgboost: Algoritmo Gradient Boosting para medicion de importancia de atributos.
- lightgbm: Algoritmo Gradient Boosting optimizado para modelado de residuos y proyeccion.
- pathlib / re / unicodedata / gc: Modulos estandar de Python para gestion de rutas, expresiones regulares, limpieza de acentos y control de memoria RAM.


6. ESTRUCTURA DE DIRECTORIOS REQUERIDA
--------------------------------------------------------------------------------
Asegurese de organizar los archivos del proyecto de la siguiente manera:

mi_proyecto/
|-- matriculaaaas/                      (Carpeta con los CSV originales 2007-2025)
|   |-- 2007.csv
|   |-- 2008.csv
|   |-- ...
|   `-- 2025.csv
|-- carreras_agrupadas.xlsx             (Matriz de homologacion en Excel)
|-- main.py                             (Script principal del codigo)
|-- requirements.txt                    (Archivo de dependencias)
`-- resultados_parquet/                 (Carpeta generada automaticamente)


7. INSTRUCCIONES DE EJECUCION
--------------------------------------------------------------------------------
1. Verifique que la carpeta "matriculaaaas" contenga los archivos CSV requeridos y que "carreras_agrupadas.xlsx" este en la raiz.
2. Abra la terminal en VS Code asegurandose de que el entorno (venv) este activo.
3. Ejecute el comando:
   python main.py

4. Al finalizar la ejecucion, revise la carpeta "resultados_parquet/", donde se habran generado las bases unificadas, reportes en formato .txt, la imagen del tablero grafico .png y las proyecciones finales para el ano 2026 en formato .parquet y .csv.