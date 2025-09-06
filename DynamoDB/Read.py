import boto3
import json
from boto3.dynamodb.conditions import Key
from DynamoDB.Utils import DynamoDBConnection
import os
from dotenv import load_dotenv
load_dotenv()
class FetchRecord:
    def __init__(self, region_name=None):
        """
        Initialize the FetchRecord class with AWS credentials and region.
        
        :param region_name: AWS region for DynamoDB (optional, defaults to env variable).
        """
        self.access_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region_name = region_name or os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

        # Initialize connection
        self.connection = DynamoDBConnection(
            access_id=self.access_id,
            secret_key=self.secret_key,
            region_name=self.region_name
        )
    # def get_aws_credentials(self):
    #     """
    #     Read AWS credentials from the JSON file.

    #     :return: Tuple of (access_id, secret_key).
    #     """
    #     try:
    #         with open(self.credentials_file, "r") as file:
    #             credentials = json.load(file)
    #         return credentials["access_id"], credentials["secret_key"]
    #     except Exception as e:
    #         raise Exception(f"Error reading AWS credentials: {e}")

    def get_data_from_table(self, table_name, key_name=None, key_value=None):
        """
        Fetch data from a DynamoDB table with an optional key filter.

        :param table_name: Name of the DynamoDB table.
        :param key_name: (Optional) Key column name to filter the data.
        :param key_value: (Optional) Value of the key column to filter the data.
        :return: List of items fetched from the table.
        """
        try:
            table = self.connection.get_table(table_name)

            if not table:
                return {"error": f"Failed to connect to table: {table_name}"}

            # If key is provided, query by that key
            if key_name and key_value:
                response = table.query(
                    KeyConditionExpression=Key(key_name).eq(key_value)
                )
                return response.get("Items", [])
            else:
                # Otherwise, scan entire table
                items = []
                response = table.scan()
                items.extend(response.get("Items", []))

                # Handle pagination
                while "LastEvaluatedKey" in response:
                    response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
                    items.extend(response.get("Items", []))

                return items
        except Exception as e:
            return {"error": str(e)}

    def get_personal_info(self, email=None):
        """
        Fetch data from the 'Personalinfo' table.

        :param email: (Optional) Filter by 'email' as the primary key.
        :return: List of items fetched.
        """
        return self.get_data_from_table(
            table_name="Personalinfo",
            key_name="email",
            key_value=email
        )

    def get_course(self, course_id=None):
        """
        Fetch data from the 'Course' table.

        :param course_id: (Optional) Filter by primary key 'Course ID'.
        :return: List of items fetched.
        """
        return self.get_data_from_table(
            table_name="Course",
            key_name="Course ID",
            key_value=course_id
        )

    def get_module(self, module_id=None):
        """
        Fetch data from the 'Module' table.

        :param module_id: (Optional) Filter by primary key 'Module ID'.
        :return: List of items fetched.
        """
        return self.get_data_from_table(
            table_name="Module",
            key_name="Module ID",
            key_value=module_id
        )

    def get_batch(self, batch_id=None, email=None):
        """
        Fetch batch details by batch_id or email.
        
        - If batch_id is provided, query by 'Batch ID'.
        - If email is provided, find 'BatchName' and then get batch data.
        """
        
        # Step 1: Fetch by Batch ID (if provided)
        if batch_id:
            print(f"🔍 Querying Batch table for Batch ID: {batch_id}")
            all_data = self.get_data_from_table("Batch", key_name="Batch ID", key_value=batch_id)
            if isinstance(all_data, dict) and "error" in all_data:
                print(f"❌ Error fetching batch by ID: {all_data['error']}")
            return all_data  # Return batch data or error

        # Step 2: If email is provided, find the corresponding BatchName
        if email:
            print(f"🔍 Scanning 'Batch' table to find BatchName for email: {email}")

            # Fetch all batches and filter manually
            all_batches = self.get_data_from_table("Batch")

            if isinstance(all_batches, dict) and "error" in all_batches:
                print(f"❌ Error scanning 'Batch' table: {all_batches['error']}")
                return all_batches

            if not isinstance(all_batches, list):
                print(f"⚠️ Unexpected response type: {type(all_batches)}. Expected list.")
                return {"error": "Unexpected data format received from DynamoDB"}

            # Filter batch record by email
            user_batches = [item for item in all_batches if item.get("email") == email]

            if not user_batches:
                print(f"⚠️ No batch found for email: {email}")
                return {"error": f"No batch record found for email: {email}"}

            # Extract BatchName
            batch_name = user_batches[0].get("BatchName", None)
            if not batch_name:
                print(f"⚠️ No 'BatchName' found for email: {email}")
                return {"error": f"Batch record exists, but no 'BatchName' found for email: {email}"}

            print(f"✅ Found BatchName '{batch_name}' for email '{email}'.")

            # Step 3: Scan again to fetch batch data by BatchName
            print(f"🔍 Scanning 'Batch' table for BatchName: {batch_name}")
            batch_records = [batch for batch in all_batches if batch.get("BatchName") == batch_name]

            if not batch_records:
                print(f"⚠️ No records found for BatchName: {batch_name}")
                return {"error": f"No batch data found for BatchName: {batch_name}"}

            print(f"✅ Retrieved {len(batch_records)} batch records for BatchName: {batch_name}")
            return batch_name

        # Step 4: If no batch_id or email is provided, return all Batch records
        print("📥 Scanning all items in the 'Batch' table...")
        all_data = self.get_data_from_table("Batch")

        if isinstance(all_data, dict) and "error" in all_data:
            print(f"❌ Error fetching all batches: {all_data['error']}")
            return all_data

        print(f"✅ Retrieved {len(all_data)} batches from 'Batch' table.")
        return all_data


    def get_student_details(self, student_id=None):
        """
        Fetch data from the 'Student Details' table by 'Student ID'.

        :param student_id: (Optional) The Student ID to filter.
        :return: List of items fetched.
        """
        return self.get_data_from_table(
            table_name="Student Details",
            key_name="Student ID",
            key_value=student_id
        )


# # Example usage
# if __name__ == "__main__":
#     # Initialize the FetchRecord object
#     fetch_record = FetchRecord()

#     # Example: Fetch data from 'Personalinfo' table
#     personal_info_data = fetch_record.get_personal_info(email="jhon@example.com")
#     print("Personal Info Data:", personal_info_data)
