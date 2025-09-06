import json
import boto3
import re
from datetime import datetime
from collections import defaultdict
from DynamoDB.Read import FetchRecord
import jwt 
import os
from DynamoDB.Read import FetchRecord

SECRET_KEY = os.environ.get("JWT_SECRET", "your-secret-key")

class RetrieveAssnAdmin:
    def __init__(self):
        with open('Credentials.json') as f:
            aws_creds = json.load(f)

        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=aws_creds["access_id"],
            aws_secret_access_key=aws_creds["secret_key"],
            region_name="us-east-1"
        )
        self.BUCKET = "generated-assignments"

    def extract_deadline_from_filename(self, filename):
        match = re.search(r'_(\d{6})\.(pdf|html|docx|ipynb)$', filename, re.IGNORECASE)
        if match:
            try:
                return datetime.strptime(match.group(1), "%d%m%y")
            except ValueError:
                return None
        return None

    def get_presigned_url(self, file_key, bucket_name):
        import mimetypes

        try:
            content_type = mimetypes.guess_type(file_key)[0] or "application/octet-stream"
            return self.s3.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': file_key,
                    'ResponseContentDisposition': f'attachment; filename="{file_key.split("/")[-1]}"',
                    'ResponseContentType': content_type
                },
                ExpiresIn=3600
            )
        except Exception as e:
            print(f"Error generating URL for {file_key} in {bucket_name}: {e}")
            return None

    def get_metadata(self, bucket, key):
        try:
            return self.s3.head_object(Bucket=bucket, Key=key).get("Metadata", {})
        except Exception as e:
            print(f"Metadata fetch failed for {key} in {bucket}: {e}")
            return {}

    def build_submissions_dict(self):
        """
        Build dict: {assignment_name: {email: {submitted_url, evaluated_url}}}
        """
        submissions = defaultdict(lambda: defaultdict(dict))

        def populate(bucket_name, url_key):
            try:
                response = self.s3.list_objects_v2(Bucket=bucket_name)
                for obj in response.get("Contents", []):
                    key = obj["Key"]
                    metadata = self.get_metadata(bucket_name, key)

                    email = metadata.get("email")
                    assignment = metadata.get("assignment_name")
                    if not (email and assignment):
                        continue

                    url = self.get_presigned_url(key, bucket_name)
                    if url is None:
                        # Skip file if URL generation fails
                        continue

                    submissions[assignment][email][url_key] = url
            except Exception as e:
                print(f"Error while processing {bucket_name}: {e}")
                return False
            return True

        if not populate("submitted-assignments", "submitted_url"):
            return None
        if not populate("evaluated-reports", "evaluated_url"):
            return None

        return submissions

    def get_file_batch_name(self, file_key):
        metadata = self.get_metadata(self.BUCKET, file_key)
        return metadata.get("batch_name")

    def process_files(self):
        valid_batches = set(self.get_batches())
        submissions_map = self.build_submissions_dict()
        if submissions_map is None:
            return {}

        response = self.s3.list_objects_v2(Bucket=self.BUCKET)
        all_files = [obj["Key"] for obj in response.get("Contents", [])]
        today = datetime.today()

        batches = defaultdict(lambda: {"ongoing": [], "archive": []})

        for file in all_files:
            deadline = self.extract_deadline_from_filename(file)
            batch_name = self.get_file_batch_name(file)

            if not batch_name or batch_name not in valid_batches or not deadline:
                continue

            assignment_name = file.rsplit("/", 1)[-1]

            # Get submissions for this assignment (dict of emails)
            assignment_submissions = submissions_map.get(assignment_name, {})

            # Convert submissions dict to list of {email: urls}
            submissions_list = [{email: urls} for email, urls in assignment_submissions.items()]

            assignment_data = {
                "name": assignment_name,
                "url": self.get_presigned_url(file, self.BUCKET),
                "deadline": deadline.strftime("%d-%m-%Y"),
                "submissions": submissions_list
            }

            if deadline >= today:
                batches[batch_name]["ongoing"].append(assignment_data)
            else:
                batches[batch_name]["archive"].append(assignment_data)

        return dict(batches)

    def get_batches(self):
        fetch_record = FetchRecord()
        data = fetch_record.get_batch()
        unique_batch_names = list({item["BatchName"] for item in data})
        return unique_batch_names


class RetrieveAssnStudent:
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

    def extract_deadline_from_filename(self, filename):
        match = re.search(r'_(\d{6})\.(pdf|html|docx|ipynb)$', filename, re.IGNORECASE)
        if match:
            try:
                return datetime.strptime(match.group(1), "%d%m%y")
            except ValueError:
                return None
        return None

    def get_presigned_url(self, file_key):
        return self.s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': self.BUCKET, 'Key': file_key},
            ExpiresIn=3600
        )

    def get_matching_file_from_bucket(self, bucket_name, assignment_name, email, batch_name):
        try:
            response = self.s3.list_objects_v2(Bucket=bucket_name)
            for obj in response.get("Contents", []):
                key = obj["Key"]
                metadata = self.s3.head_object(Bucket=bucket_name, Key=key).get("Metadata", {})
                if (
                    metadata.get("assignment_name") == assignment_name
                    and metadata.get("email") == email
                    and metadata.get("batch_name") == batch_name
                ):
                    return self.s3.generate_presigned_url(
                        ClientMethod="get_object",
                        Params={"Bucket": bucket_name, "Key": key},
                        ExpiresIn=3600
                    )
        except Exception as e:
            print(f"Error retrieving from {bucket_name}: {e}")
        return None


    def get_file_batch_name(self, file_key):
        try:
            response = self.s3.head_object(Bucket=self.BUCKET, Key=file_key)
            metadata = response.get("Metadata", {})
            return metadata.get("batch_name")
        except Exception as e:
            print(f"Error fetching metadata for {file_key}: {e}")
            return None

    def get_batch_of_mail(self,email):
        fetch_record = FetchRecord()
        data = fetch_record.get_batch(None,email)
        return data


    def process_files(self, email):
        batch_name = self.get_batch_of_mail(email)  # Assume this returns a string, not a list
        if not batch_name:
            return {}

        response = self.s3.list_objects_v2(Bucket=self.BUCKET)
        files = [obj["Key"] for obj in response.get("Contents", [])]

        today = datetime.today()
        batch_files = {"ongoing": [], "archive": []}

        for file in files:
            deadline = self.extract_deadline_from_filename(file)
            file_batch_name = self.get_file_batch_name(file)

            if file_batch_name != batch_name or not deadline:
                continue

            file_data = {
                "name": file,
                "url": self.get_presigned_url(file),
                "deadline": deadline.strftime("%d-%m-%Y")
            }

            if deadline >= today:
                batch_files["ongoing"].append(file_data)
            else:
                # Add extra logic for submitted and evaluated files
                assignment_name = file.rsplit("/", 1)[-1]  # Get filename only
                submitted_url = self.get_matching_file_from_bucket(
                    "submitted-assignments", assignment_name, email, batch_name
                )
                evaluated_url = self.get_matching_file_from_bucket(
                    "evaluated-reports", assignment_name, email, batch_name
                )
                
                file_data["submitted_url"] = submitted_url
                file_data["evaluated_url"] = evaluated_url
                batch_files["archive"].append(file_data)

        return {batch_name: batch_files}
    {
        "ongoing":[],
        "archive":[]
    }

class RetrieveAll:
    
    def retriever(event, context):
        request = context.get("request", {})
        auth_header = request.get("headers", {}).get("Authorization", "")
        obk = FetchRecord()

        

        if not auth_header.startswith("Bearer "):
            return "No Header Found"

        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        email = payload["email"]
        print(email)
        role_data = obk.get_data_from_table("Roles", "user_id", email)
        role = role_data[0]['role']
        print(role)
        # body = json.loads(event["body"])
        # print("BODY:", body) 
        # email = body.get('email')
        # role = body.get('role')
        if role == "student":
            try:
                print("EVENT:", event)

                obj = RetrieveAssnStudent()
                
                batch_files = obj.process_files(email)
                print(batch_files)
                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*",
                    },
                    "body": json.dumps(batch_files)
                }

            except Exception as e:
                return {
                    "statusCode": 500,
                    "body": json.dumps({"error": str(e)})
            }
        if role == "admin":
            try:
                print("EVENT:", context)

                obj = RetrieveAssnAdmin()
                print('test1')
                # body = json.loads(context.get("body"))

                print('test2')
                # print("BODY:", body)


                batch_names = obj.get_batches()
                batch_files = obj.process_files()
                batches_and_assn = {
                    "batch_names":batch_names,
                    "assignments":batch_files
                }
                return {
                    "statusCode": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*",
                    },
                    "body": json.dumps(batches_and_assn)
                }

                # batch_files = obj.process_files()

                # return {
                #     "statusCode": 200,
                #     "headers": {
                #         "Content-Type": "application/json",
                #         "Access-Control-Allow-Origin": "*",
                #     },
                #     "body": json.dumps(batch_files)
                    
                # }

            except Exception as e:
                return {
                    "statusCode": 500,
                    "body": json.dumps({"error": str(e)})
                }

