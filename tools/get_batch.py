import json
from DynamoDB.Read import FetchRecord  


class GetBatchMail:
    def getBatches(self, event, context=None):
        """
        AWS Lambda function to retrieve batch details.
        This function expects query parameters like 'email' or 'batch_id' (optional).
        """

        # Instantiate the FetchRecord class
        fetch_record = FetchRecord()

        # Fetch data from DynamoDB
        data = fetch_record.get_batch()
        print("Data:", data)

        # Get unique batch names from the data
        unique_batch_names = list({item.get("BatchName") for item in data if item.get("BatchName")})
        print("unique_batch_names:", unique_batch_names)


        test = {batch_name: [] for batch_name in unique_batch_names}

        # Fill in emails for each batch
        for item in data:
            batch_name = item.get("BatchName")
            email = item.get("email")

            # Ensure both keys exist before using
            if batch_name in test and email:
                test[batch_name].append(email)

        # Prepare the HTTP response
        response = {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"  # Allow all origins (CORS)
            },
            "body": json.dumps(test)  # Convert dictionary to JSON string
        }

        return response
