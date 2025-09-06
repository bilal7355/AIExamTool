import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import boto3
from dateutil import parser
from datetime import datetime

# Load Gmail credentials from environment variables
GMAIL_USER = "craftingbrainofficial@gmail.com"
GMAIL_PASS ="ehts dcvb lyme kabo" 

class Email:
    def __init__(self):
        with open('assignments/Credentials.json') as f:
            aws_creds = json.load(f)

        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=aws_creds["access_id"],
            aws_secret_access_key=aws_creds["secret_key"],
            region_name="us-east-1"
        )
        self.BUCKET = "generated-assignments"
    def sanitize_filename(self, topic):
        """Sanitize topic name for a safefilename."""
        return re.sub(r"[^a-zA-Z0-9_]+", "_", topic.lower().strip())  
    
    def to_dmy_format(self,date_str):
        date_str = date_str.strip()
        if len(date_str) == 6 and date_str.isdigit():
            # Directly treat as DDMMYY
            try:
                parsed_date = datetime.strptime(date_str, "%d%m%y")
                return parsed_date.strftime("%d%m%y")  # keeps it in dmy
            except ValueError:
                return "Invalid Deadline"

        # Fallback to parser for other human-readable formats
        try:
            from dateutil import parser
            parsed_date = parser.parse(date_str, dayfirst=True)
            return parsed_date.strftime("%d%m%y")
        except Exception:
            return "Invalid Deadline"
    
    def get_presigned_url(self, file_key):
        import mimetypes

        try:
            content_type = mimetypes.guess_type(file_key)[0] or "application/octet-stream"
            return self.s3.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': "generated-assignments",
                    'Key': file_key,
                    'ResponseContentDisposition': f'attachment; filename="{file_key.split("/")[-1]}"',
                    'ResponseContentType': content_type
                },
                ExpiresIn=3600
            )
        except Exception as e:
            print(f"Error generating URL: {e}")
            return None
        
    def send_email(self,to_emails, subject, message):
        """Send an email using Gmail SMTP"""
        if not to_emails:
            return {"status": "failed", "message": "No recipients found"}

        try:
            msg = MIMEMultipart()
            msg["From"] = GMAIL_USER
            msg["To"] = ", ".join(to_emails)
            msg["Subject"] = subject

            msg.attach(MIMEText(message, "plain"))

            # Connect to Gmail SMTP server
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to_emails, msg.as_string())
            server.quit()

            return {"status": "success", "message": "Emails sent successfully"}
        except Exception as e:
            return {"status": "failed", "message": str(e)}


    def mailer(self, event):
        try:
            print("EVENT RECEIVED:", event)  # Debug
            body = event['request'].get('body')
            body = json.loads(body)
            emails = body.get('recipients')
            subject = body.get("subject", "No Subject")
            message = body.get("message", "No Message")
            topic = body.get("topic")
            deadline = body.get("deadline")
            if deadline:
                deadline = self.to_dmy_format(deadline)
            extension = body.get("extension")
            filename = f"assignment_{(topic)}_{deadline}.{extension}"
            url = self.get_presigned_url(filename)
            if url:
                message += f"\n\nDownload your assignment here (valid for a few minutes):\n{url}"

            result = self.send_email(emails, subject, message)

            print("Recipients:", emails)

            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
                    "Access-Control-Allow-Headers": "Content-Type"
                },
                "body": json.dumps(result)
            }

        except Exception as e:
            return {
                "statusCode": 500,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
                    "Access-Control-Allow-Headers": "Content-Type"
                },
                "body": json.dumps({"error": str(e)})
            }
