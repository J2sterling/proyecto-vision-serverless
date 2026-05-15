import json
import uuid
import boto3
import os

s3 = boto3.client('s3')
sqs = boto3.client('sqs')

BUCKET_NAME = os.environ['BUCKET_NAME']
QUEUE_URL = os.environ['QUEUE_URL']

def lambda_handler(event, context):
    try:
        body = event.get('body', '')
        headers = event.get('headers', {})
        content_type = headers.get('content-type', '')

        is_base64 = event.get('isBase64Encoded', False)
        if is_base64:
            import base64
            body = base64.b64decode(body)

        if content_type.startswith('application/json'):
            data = json.loads(body)
            image_base64 = data.get('image', '')
            if image_base64:
                image_bytes = base64.b64decode(image_base64)
            else:
                raise ValueError("No se encontró campo 'image' en el JSON")
        else:
            image_bytes = body

        image_id = str(uuid.uuid4())
        key = f"{image_id}.jpg"

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=image_bytes,
            ContentType='image/jpeg'
        )

        message = {
            'image_id': image_id,
            'key': key
        }
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(message))

        return {
            'statusCode': 202,
            'body': json.dumps({
                'message': 'Imagen aceptada',
                'image_id': image_id
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
