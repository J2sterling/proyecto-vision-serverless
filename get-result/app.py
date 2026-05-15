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
        # Convertir Decimal a float para serialización JSON
        def convert(obj):
            if isinstance(obj, Decimal):
                return float(obj) if obj % 1 != 0 else int(obj)
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [convert(i) for i in obj]
            return obj
        
        return {
            'statusCode': 200,
            'body': json.dumps(convert(item), indent=2, ensure_ascii=False)
        }
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
