import json
import boto3
import re
import os
from datetime import datetime
from uuid import uuid4
from io import BytesIO
import base64

class UploadAssn:
    def upload(self,event, context=None):
        try:
            # If using Lambda Proxy Integration, event["body"] contains JSON string
            body = event['request'].get("body")
            if body is None:
                raise Exception("Missing body in event")

            # Parse the JSON string body to dict
            data = json.loads(body)

            # Extract file, filename, metadata
            file_data = base64.b64decode(data["file"])
            filename = data.get("filename","")
            metadata = data.get("metadata", {})

            file_buffer = BytesIO(file_data)

            # Upload
            result = self.upload_pdf_to_s3(file_buffer, filename, metadata)

            return {
                "statusCode": 200,
                "body": json.dumps(result),
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                }
            }

        except Exception as e:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": str(e)}),
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                }
            }



    def upload_pdf_to_s3(self,file_buffer, filename, metadata):
        # Choose S3 credentials source
        if os.environ.get("USE_LAMBDA_CREDS", "true").lower() == "true":
            s3 = boto3.client("s3")
        else:
            with open('Credentials.json') as f:
                aws_creds = json.load(f)

            s3 = boto3.client(
                "s3",
                aws_access_key_id=aws_creds["access_id"],
                aws_secret_access_key=aws_creds["secret_key"],
                region_name="us-east-1"
            )

        BUCKET = "submitted-assignments"

        # Determine content type
        content_type_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".html": "text/html",
            ".ipynb": "application/x-ipynb+json"
        }

        ext = '.' + filename.split('.')[-1].lower()
        if ext not in content_type_map:
            return {"error": "Unsupported file type"}

        content_type = content_type_map.get(ext, 'application/octet-stream')
        extra_args = {'ContentType': content_type}

        if metadata:
            extra_args['Metadata'] = {str(k): str(v) for k, v in metadata.items()}

        safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', os.path.basename(filename))
        key = f"assignments/{datetime.now().strftime('%Y-%m-%d')}/{uuid4().hex}_{safe_filename}"

        # Upload to S3
        try:
            file_buffer.seek(0)
            s3.upload_fileobj(
                file_buffer,
                BUCKET,
                key,
                ExtraArgs=extra_args
            )
            return {"url": f"https://{BUCKET}.s3.amazonaws.com/{key}"}
        except Exception as e:
            print(f"Upload failed: {str(e)}")
            return {"error": "S3 upload failed", "details": str(e)}
