import json
import os
import time
import uuid
import boto3
from decimal import Decimal

# ── Configuración (ajusta si es necesario) ─────────────────────
BUCKET = "proyecto-vision-serverless"                     # <-- confirma el nombre de tu bucket
QUEUE_URL = "https://sqs.us-east-2.amazonaws.com/035949051644/imagenes-procesamiento-queue"
TABLE_NAME = "resultados-vision"
DATASET_JSON = "../dataset/ground_truth.json"             # ruta desde proyecto-vision/
IMAGENES_DIR = "../dataset/imagenes"
LIMIT = 100                                                # procesar todas las imágenes

# Clientes de AWS
s3 = boto3.client('s3')
sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

# ── Funciones auxiliares (las mismas del Lambda) ──────────────
def jaccard_similarity(list1, list2):
    set1 = set(normalizar(item) for item in list1)
    set2 = set(normalizar(item) for item in list2)
    if not set1 and not set2:
        return 1.0
    inter = set1 & set2
    union = set1 | set2
    return len(inter) / len(union) if union else 0.0

def normalizar(texto):
    return texto.strip().lower()

def texto_similar(gt_text, api_text):
    if not gt_text and not api_text:
        return 1.0
    if not gt_text or not api_text:
        return 0.0
    return 1.0 if gt_text.strip().lower() == api_text.strip().lower() else 0.0

def safe_search_igual(gt, api):
    def normalizar_safe(val):
        if isinstance(val, str):
            return val.upper()
        if isinstance(val, (int, float)):
            # Google devuelve 1=VERY_UNLIKELY, 2=UNLIKELY, 3=POSSIBLE, 4=LIKELY, 5=VERY_LIKELY
            mapeo = {1: 'VERY_UNLIKELY', 2: 'UNLIKELY', 3: 'POSSIBLE', 4: 'LIKELY', 5: 'VERY_LIKELY'}
            return mapeo.get(int(val), 'UNKNOWN')
        return 'UNKNOWN'
    try:
        return 1.0 if (normalizar_safe(api.get('adult')) == normalizar_safe(gt['adult'])
                   and normalizar_safe(api.get('violence')) == normalizar_safe(gt['violence'])
                   and normalizar_safe(api.get('racy')) == normalizar_safe(gt['racy'])) else 0.0
    except:
        return 0.0

# ── Procesamiento principal ─────────────────────────────────
def main():
    with open(DATASET_JSON, 'r', encoding='utf-8') as f:
        ground_truth = json.load(f)[:LIMIT]

    resultados = []
    total = len(ground_truth)
    print(f"Iniciando procesamiento local de {total} imágenes...")

    for i, gt in enumerate(ground_truth):
        image_file = gt['image_id']
        local_path = f"{IMAGENES_DIR}/{image_file}"

        # Leer imagen del disco
        try:
            with open(local_path, 'rb') as img:
                image_bytes = img.read()
        except FileNotFoundError:
            print(f"No se encontró {local_path}, saltando.")
            continue

        # Subir a S3 y encolar
        image_id = str(uuid.uuid4())
        key = f"{image_id}.jpg"
        s3.put_object(Bucket=BUCKET, Key=key, Body=image_bytes, ContentType='image/jpeg')
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({'image_id': image_id, 'key': key}))

        # Esperar a que process-image termine (hasta 2 min)
        print(f"Esperando procesamiento de {image_file} (ID: {image_id})...")
        item = None
        for _ in range(18):   
            time.sleep(10)
            resp = table.get_item(Key={'image_id': image_id})
            if 'Item' in resp:
                item = resp['Item']
                break

        if not item:
            print(f"Timeout esperando {image_id}, se omite.")
            continue

        google = item.get('google', {})
        azure = item.get('azure', {})

        # Comparar con ground truth
        comparacion = {
            'image_file': image_file,
            'image_id': image_id,
            'google': {
                'objects_match': jaccard_similarity(gt['objects'], [o['name'] for o in google.get('objects', [])]),
                'ocr_match': texto_similar(gt['ocr_text'], google.get('ocr_text', '')),
                'safe_search_match': safe_search_igual(gt['explicit_content'], google.get('explicit_content', {})),
                'landmarks_match': jaccard_similarity(gt['landmarks'], [l['description'] for l in google.get('landmarks', [])])
            },
            'azure': {
                'objects_match': jaccard_similarity(gt['objects'], [o['name'] for o in azure.get('objects', [])]),
                'ocr_match': texto_similar(gt['ocr_text'], azure.get('ocr_text', '')),
                'safe_search_match': safe_search_igual(gt['explicit_content'], azure.get('explicit_content', {})),
                'landmarks_match': 0.0   # Azure no tiene landmarks
            }
        }
        resultados.append(comparacion)
        print(f"Procesado {i+1}/{total}")

        # Pausa para no exceder el límite de Azure (20 peticiones/min)
        time.sleep(5)

    # ── Guardar resultados ──────────────────────────────────
    with open('resultados_comparacion.json', 'w', encoding='utf-8') as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)
    print("Resultados detallados guardados en 'resultados_comparacion.json'")

    # ── Métricas globales ───────────────────────────────────
    if resultados:
        g_obj = sum(r['google']['objects_match'] for r in resultados) / len(resultados)
        a_obj = sum(r['azure']['objects_match'] for r in resultados) / len(resultados)
        g_ocr = sum(r['google']['ocr_match'] for r in resultados) / len(resultados)
        a_ocr = sum(r['azure']['ocr_match'] for r in resultados) / len(resultados)
        g_safe = sum(r['google']['safe_search_match'] for r in resultados) / len(resultados)
        a_safe = sum(r['azure']['safe_search_match'] for r in resultados) / len(resultados)
        g_land = sum(r['google']['landmarks_match'] for r in resultados) / len(resultados)
    else:
        g_obj = a_obj = g_ocr = a_ocr = g_safe = a_safe = g_land = 0.0

    print("\n===== RESULTADOS FINALES =====")
    print(f"Total de imágenes procesadas: {len(resultados)}")
    print(f"Objetos    - Google: {g_obj:.3f}, Azure: {a_obj:.3f}")
    print(f"OCR        - Google: {g_ocr:.3f}, Azure: {a_ocr:.3f}")
    print(f"Safe Search- Google: {g_safe:.3f}, Azure: {a_safe:.3f}")
    print(f"Landmarks  - Google: {g_land:.3f}, Azure: N/A")

if __name__ == '__main__':
    main()
