import boto3
import json
import urllib.parse

def lambda_handler(event, context):
    glue = boto3.client('glue', region_name='ap-south-1')
    
    # Get file details from S3 event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(
        event['Records'][0]['s3']['object']['key']
    )
    
    print(f"New file detected: s3://{bucket}/{key}")
    print(f"Triggering Glue ETL pipeline...")
    
    # Trigger Glue ETL job
    response = glue.start_job_run(
        JobName='pharma elt job'
    )
    
    job_run_id = response['JobRunId']
    print(f"Glue job started: {job_run_id}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Pipeline triggered',
            'file': key,
            'glue_run_id': job_run_id
        })
    }