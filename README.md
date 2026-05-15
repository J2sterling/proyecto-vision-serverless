
# Plataforma Serverless de Procesamiento de Imágenes con Visión Computacional

Proyecto académico que implementa una **arquitectura serverless** en AWS para procesar imágenes con dos APIs de visión computacional — **Google Cloud Vision** y **Azure AI Vision** —, almacenar los resultados y exponer una API REST segura con comparativa de precisión, latencia y costos.

---

## 🧠 Descripción general

La plataforma permite:

- **Subir imágenes** a través de un endpoint REST (`POST /images`).
- **Procesarlas automáticamente** con Google Cloud Vision y Azure AI Vision (detección de objetos, OCR, contenido explícito, landmarks).
- **Almacenar los resultados** unificados en DynamoDB.
- **Consultar los resultados** individuales o comparar ambas APIs.
- **Ejecutar un análisis masivo** sobre un dataset etiquetado de 100 imágenes para medir precisión, latencia y costos.

Todo desplegado con **Infraestructura como Código (SAM)** y protegido con **API Key y rate limiting**.

---

## 🛠️ Tecnologías y servicios utilizados

| Herramienta / Servicio       | Propósito |
|------------------------------|-----------|
| **AWS Lambda**               | Ejecución de código serverless (4 funciones). |
| **Amazon S3**                | Almacenamiento de imágenes subidas. |
| **Amazon SQS**               | Cola de mensajes para desacoplar subida y procesamiento. |
| **Amazon DynamoDB**          | Base de datos NoSQL para resultados. |
| **Amazon API Gateway**       | Exposición de la API REST (con autenticación y rate limiting). |
| **AWS SAM**                  | Infraestructura como código (template.yaml). |
| **Google Cloud Vision API**  | Detección de objetos, OCR, contenido explícito, landmarks. |
| **Azure AI Vision**          | Detección de objetos, OCR, contenido adulto/racy. |
| **Swagger UI**               | Documentación interactiva de la API. |
| **Python 3.12**              | Lenguaje de las funciones Lambda. |
| **AWS CLI**                  | Interacción con los servicios AWS. |

---

## 🔒 Archivos no incluidos en el repositorio

Por seguridad, **no se suben** los archivos que contienen credenciales o configuraciones sensibles:

| Archivo | Contenido | ¿Por qué no se sube? |
|---------|-----------|----------------------|
| `samconfig.toml` | Parámetros de despliegue (`parameter_overrides`) con claves de API. | Contiene las credenciales de Google Cloud Vision y Azure AI Vision. |
| `.env` | Variables de entorno para ejecución local. | Ídem. |


### 📝 Ejemplo del archivo `samconfig.toml`

```toml
version = 0.1

[default.deploy.parameters]
stack_name = "proyect-vision-serveless"
region = "us-east-2"
capabilities = "CAPABILITY_NAMED_IAM"
parameter_overrides = "GoogleCredentialsJson='{\"type\":\"service_account\",...}' AzureVisionKey='...' AzureVisionEndpoint='https://.../'"
```

El valor de `GoogleCredentialsJson` es el contenido completo del archivo JSON de la cuenta de servicio de Google, escapado en una sola línea.



## ⚙️ Instalación de herramientas necesarias

### 1. Python 3.12

La función Lambda que procesa las imágenes (`process-image`) utiliza **Python 3.12** porque las librerías de Google Cloud Vision y Azure requieren esta versión (o superior) para funcionar correctamente en el entorno serverless.

En Ubuntu:

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv
```

Crear un entorno virtual (recomendado):

```bash
python3.12 -m venv venv312
source venv312/bin/activate
```

### 2. AWS CLI

```bash
sudo apt install -y awscli
aws configure
```

Introduce tu Access Key, Secret Key, región (`us-east-2`) y formato (`json`).

### 3. AWS SAM CLI

```bash
pip install aws-sam-cli
```

---

## 📁 Estructura del proyecto

```
proyecto-vision/
├── template.yaml              # Infraestructura como código (SAM)
├── openapi.yaml               # Definición OpenAPI 3.0
├── analisis_local.py          # Script para análisis masivo del dataset
├── upload-image/              # Código de la Lambda de subida
│   └── app.py
├── process-image/             # Código de la Lambda de procesamiento
│   ├── app.py
│   └── requirements.txt       # Dependencias (google-cloud-vision, azure…)
├── get-result/                # Lambda de consulta de resultados
│   └── app.py
├── compare/                   # Lambda de comparación entre APIs
│   └── app.py
├── dataset/
│   ├── ground_truth.json      # Etiquetas de las 100 imágenes
│   └── imagenes/              # Archivos .jpg del dataset
└── .gitignore
```

---

## 🚀 Despliegue

1. **Construir**:
   ```bash
   sam build
   ```
2. **Desplegar** :
   ```bash
   sam deploy 
   ```
   

3. **Obtener la API Key**:
   ```bash
   aws apigateway get-api-keys --region us-east-2 --query "items[?name=='ProyectoVisionApiKey'].value" --output text
   ```

---

## 🧪 Pruebas

### Subir una imagen

```bash
curl -X POST "https://<tu-api>/Prod/images" \
  -H "Content-Type: application/octet-stream" \
  -H "x-api-key: TU_API_KEY" \
  --data-binary @imagen.jpg
```

### Obtener resultados

```bash
curl "https://<tu-api>/Prod/images/<image_id>" -H "x-api-key: TU_API_KEY"
```

### Comparar APIs

```bash
curl "https://<tu-api>/Prod/images/<image_id>/comparison" -H "x-api-key: TU_API_KEY"
```

### Análisis masivo del dataset

```bash
python3 analisis_local.py
```

Genera `resultados_comparacion.json` con las métricas de las 100 imágenes.

---

## 📊 Dashboard y alertas

Se configuraron en **CloudWatch**:

- **Dashboard** con widgets de invocaciones, latencia, errores y mensajes SQS.
- **Alarma** `ProyectoVision-ErrorAlarm`: se activa si hay más de 5 errores en 5 minutos.
- **Alarma** `ProyectoVision-LatencyAlarm`: se activa si la duración promedio supera los 30 segundos.

Ambas envían notificaciones por correo a través de un tema SNS.

---
