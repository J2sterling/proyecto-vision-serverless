import json
import os
import time
import boto3
from io import BytesIO
import requests
from decimal import Decimal


from google.cloud import vision
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])
bucket_name = os.environ['BUCKET_NAME']

google_creds_json = os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON']
google_creds = json.loads(google_creds_json)

azure_key = os.environ['AZURE_VISION_KEY']
azure_endpoint = os.environ['AZURE_VISION_ENDPOINT']
azure_client = ComputerVisionClient(azure_endpoint, CognitiveServicesCredentials(azure_key))

def lambda_handler(event, context):
    for record in event['Records']:
        try:
            body = json.loads(record['body'])
            image_id = body['image_id']
            key = body['key']

            image_obj = s3.get_object(Bucket=bucket_name, Key=key)
            image_content = image_obj['Body'].read()

            # Google
            print(f"Procesando {image_id} con Google...")
            t0 = time.time()
            google_result = analyze_with_google(image_content)
            google_latency = int((time.time() - t0) * 1000)

            # Azure
            print(f"Procesando {image_id} con Azure...")
            t1 = time.time()
            azure_result = analyze_with_azure(image_content)
            azure_latency = int((time.time() - t1) * 1000)

            google_cost = Decimal('0.003')
            azure_cost = Decimal('0.0012')

            item = {
                'image_id': image_id,
                'google': google_result,
                'azure': azure_result,
                'latency_ms': {'google': google_latency, 'azure': azure_latency},
                'cost_estimate': {'google': google_cost, 'azure': azure_cost},
                'timestamp': int(time.time())
            }

            # Conversión de floats a Decimal (necesario para DynamoDB)
            def convert_floats(obj):
                if isinstance(obj, float):
                    return Decimal(str(obj))
                elif isinstance(obj, dict):
                    return {k: convert_floats(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_floats(i) for i in obj]
                return obj

            item = convert_floats(item)
            table.put_item(Item=item)
            print(f"Resultado guardado para {image_id}")

        except Exception as e:
            print(f"Error procesando mensaje: {e}")
            continue

def analyze_with_google(image_bytes):
    client = vision.ImageAnnotatorClient.from_service_account_info(google_creds)
    image = vision.Image(content=image_bytes)

    # Objetos
    objects = []
    try:
        resp = client.object_localization(image=image)
        for obj in resp.localized_object_annotations:
            objects.append({'name': obj.name, 'confidence': round(obj.score, 4)})
    except Exception as e:
        print(f"Google Objects error: {e}")

    # OCR
    ocr_text = ''
    try:
        resp = client.text_detection(image=image)
        if resp.text_annotations:
            ocr_text = resp.text_annotations[0].description.strip()
    except Exception as e:
        print(f"Google OCR error: {e}")

    # Safe Search
    try:
        safe = client.safe_search_detection(image=image)
        safe_result = {
            'adult': str(safe.safe_search_annotation.adult),
            'violence': str(safe.safe_search_annotation.violence),
            'racy': str(safe.safe_search_annotation.racy)
        }
    except Exception as e:
        print(f"Google SafeSearch error: {e}")
        safe_result = {'adult': 'UNKNOWN', 'violence': 'UNKNOWN', 'racy': 'UNKNOWN'}

    # Landmarks
    landmarks = []
    try:
        resp = client.landmark_detection(image=image)
        for landmark in resp.landmark_annotations:
            landmarks.append({'description': landmark.description, 'confidence': round(landmark.score, 4)})
    except Exception as e:
        print(f"Google Landmarks error: {e}")

    return {
        'objects': objects,
        'ocr_text': ocr_text,
        'explicit_content': safe_result,
        'landmarks': landmarks
    }


def analyze_with_azure(image_bytes):
    headers = {
        'Ocp-Apim-Subscription-Key': azure_key,
        'Content-Type': 'application/octet-stream'
    }
    base_url = azure_endpoint.rstrip('/') + '/vision/v3.2/'

    # Objetos
    objects = []
    try:
        resp = requests.post(
            base_url + 'detect?visualFeatures=Objects',
            headers=headers,
            data=image_bytes
        )
        resp.raise_for_status()
        data = resp.json()
        for obj in data.get('objects', []):
            objects.append({
                'name': obj['object'],
                'confidence': round(obj['confidence'], 4)
            })
    except Exception as e:
        print(f"Azure Objects error: {e}")

    # OCR asíncrono
    ocr_text = ''
    try:
        ocr_resp = requests.post(
            base_url + 'read/analyze',
            headers=headers,
            data=image_bytes
        )
        ocr_resp.raise_for_status()
        operation_url = ocr_resp.headers['Operation-Location']
        for _ in range(20):
            result_resp = requests.get(operation_url, headers={'Ocp-Apim-Subscription-Key': azure_key})
            if result_resp.status_code == 200:
                result = result_resp.json()
                if result['status'] == 'succeeded':
                    for read_result in result['analyzeResult']['readResults']:
                        for line in read_result['lines']:
                            ocr_text += line['text'] + '\n'
                    break
            time.sleep(0.5)
    except Exception as e:
        print(f"Azure OCR error: {e}")

    # Contenido adulto/racy
    safe = {'adult': 'UNKNOWN', 'violence': 'UNKNOWN', 'racy': 'UNKNOWN'}
    try:
        resp = requests.post(
            base_url + 'analyze?visualFeatures=Adult',
            headers=headers,
            data=image_bytes
        )
        resp.raise_for_status()
        data = resp.json()
        adult = data.get('adult', {})
        safe['adult'] = 'LIKELY' if adult.get('adultScore', 0) > 0.5 else 'UNLIKELY'
        safe['racy'] = 'LIKELY' if adult.get('racyScore', 0) > 0.5 else 'UNLIKELY'
    except Exception as e:
        print(f"Azure SafeSearch error: {e}")

    return {
        'objects': objects,
        'ocr_text': ocr_text.strip(),
        'explicit_content': safe,
        'landmarks': []
    }
