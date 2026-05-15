import json
import os
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

def lambda_handler(event, context):
    try:
        image_id = event['pathParameters']['image_id']
        response = table.get_item(Key={'image_id': image_id})
        if 'Item' not in response:
            return {'statusCode': 404, 'body': json.dumps({'error': 'No encontrado'})}

        item = response['Item']

        # ── Conversión de Decimal a tipos nativos ─────────────────
        def convert(obj):
            if isinstance(obj, Decimal):
                return float(obj) if obj % 1 != 0 else int(obj)
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [convert(i) for i in obj]
            return obj

        item = convert(item)

        google = item.get('google', {})
        azure = item.get('azure', {})

        # Comparación de objetos (Jaccard)
        google_objs = [obj['name'] for obj in google.get('objects', [])]
        azure_objs = [obj['name'] for obj in azure.get('objects', [])]

        if not google_objs and not azure_objs:
            jaccard = 0
        else:
            intersection = set(google_objs) & set(azure_objs)
            union = set(google_objs) | set(azure_objs)
            jaccard = len(intersection) / len(union) if union else 0

        # Coincidencia en safe search (aproximada)
        google_safe = google.get('explicit_content', {})
        azure_safe = azure.get('explicit_content', {})
        safe_match = google_safe.get('adult') == azure_safe.get('adult') and \
                     google_safe.get('racy') == azure_safe.get('racy')

        # Diferencia de latencia
        lat_google = item.get('latency_ms', {}).get('google', 0)
        lat_azure = item.get('latency_ms', {}).get('azure', 0)
        lat_diff = lat_azure - lat_google

        # Comparación de costos
        cost_google = item.get('cost_estimate', {}).get('google', 0)
        cost_azure = item.get('cost_estimate', {}).get('azure', 0)
        cheaper = 'google' if cost_google < cost_azure else 'azure'

        comparison = {
            'image_id': image_id,
            'objects_jaccard_similarity': round(jaccard, 4),
            'google_objects': google_objs,
            'azure_objects': azure_objs,
            'common_objects': list(intersection) if union else [],
            'safe_search_match': safe_match,
            'latency_diff_ms': lat_diff,
            'cost_comparison': {
                'google': cost_google,
                'azure': cost_azure,
                'cheaper_api': cheaper
            }
        }

        return {
            'statusCode': 200,
            'body': json.dumps(comparison, indent=2)
        }

    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
