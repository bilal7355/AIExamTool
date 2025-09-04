#!/usr/bin/env python3
"""
generate_assignment_report.py
Creates one Excel file per assignment with all submissions up to a deadline,
joined with Students table metadata (name, email, college, class_code).
"""

import argparse
import os
import boto3
import pandas as pd
from dateutil import parser as dateparser
import yaml
from boto3.dynamodb.conditions import Attr, Key
from decimal import Decimal
from typing import Dict, Any, List

# 🔑 Replace these with your actual AWS credentials
AWS_ACCESS_KEY_ID = "AKIAXNGUVEBEEXXJ22GW"
AWS_SECRET_ACCESS_KEY = "tjzEOyGTnTFc81i+MnwMX07XWYIIq8lDYdq01nft"
AWS_REGION = "us-east-1"   # change to your region

def load_config(path="config.yaml"):
    if os.path.exists(path):
        with open(path, "r") as f:
            return yaml.safe_load(f)
    return {}

def init_dynamodb(region_name=None):
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=region_name or AWS_REGION
    )
    return session.resource('dynamodb')

def convert_types(obj):
    """Recursively convert Decimal to int/float for pandas compatibility."""
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: convert_types(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_types(v) for v in obj]
    return obj

def scan_table_all(table, filter_expression=None):
    kwargs = {}
    if filter_expression is not None:
        kwargs['FilterExpression'] = filter_expression
    items = []
    resp = table.scan(**kwargs)
    items.extend(resp.get('Items', []))
    while 'LastEvaluatedKey' in resp:
        kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']
        resp = table.scan(**kwargs)
        items.extend(resp.get('Items', []))
    return [convert_types(i) for i in items]

def fetch_students_map(dynamodb, students_table_name: str):
    table = dynamodb.Table(students_table_name)
    items = scan_table_all(table)
    by_id = {}
    by_email = {}
    for it in items:
        sid = it.get('student_id') or it.get('id')
        email = it.get('email')
        if sid:
            by_id[str(sid)] = it
        if email:
            by_email[email] = it
    return by_id, by_email

def fetch_evaluations(dynamodb, evaluations_table_name: str, assignment_id: str) -> List[Dict[str, Any]]:
    table = dynamodb.Table(evaluations_table_name)
    try:
        response = table.query(KeyConditionExpression=Key('assignment_id').eq(assignment_id))
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.query(KeyConditionExpression=Key('assignment_id').eq(assignment_id),
                                   ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))
        return [convert_types(i) for i in items]
    except Exception:
        filt = Attr('assignment_id').eq(assignment_id)
        return scan_table_all(table, filt)

def parse_dt(dt_str):
    if dt_str is None:
        return None
    try:
        return dateparser.parse(dt_str)
    except Exception:
        return None

def generate_report(dynamodb, cfg, assignment_id, class_code=None, deadline=None, output_path=None, upload_to_s3=False):
    students_table = cfg.get('students_table', 'Students')
    evaluations_table = cfg.get('evaluations_table', 'Evaluations')
    s3_bucket = cfg.get('s3_bucket')
    output_folder = cfg.get('output_folder', './reports')

    os.makedirs(output_folder, exist_ok=True)
    if output_path is None:
        suffix = class_code if class_code else "allclasses"
        output_path = os.path.join(output_folder, f"{assignment_id}_{suffix}.xlsx")

    print("Fetching students...")
    students_by_id, students_by_email = fetch_students_map(dynamodb, students_table)

    print("Fetching evaluations for assignment:", assignment_id)
    evaluations = fetch_evaluations(dynamodb, evaluations_table, assignment_id)

    deadline_dt = parse_dt(deadline) if deadline else None

    rows = []
    for ev in evaluations:
        ev = convert_types(ev)
        sub_time = parse_dt(ev.get('submission_time') or ev.get('submitted_at') or ev.get('time'))
        if deadline_dt and sub_time and sub_time > deadline_dt:
            continue

        student = None
        if 'student_id' in ev and ev.get('student_id') is not None:
            student = students_by_id.get(str(ev.get('student_id')))
        if not student and ev.get('student_email'):
            student = students_by_email.get(ev.get('student_email'))

        student_class = (student.get('class_code') if student else None) or ev.get('class_code')
        if class_code and student_class and student_class != class_code:
            continue

        row = {
            "assignment_id": ev.get('assignment_id'),
            "submission_id": ev.get('submission_id') or ev.get('id') or None,
            "submission_time": sub_time.isoformat() if sub_time else ev.get('submission_time'),
            "student_id": ev.get('student_id'),
            "student_name": (student.get('name') if student else ev.get('student_name') or ""),
            "student_email": ev.get('student_email') or (student.get('email') if student else ""),
            "college": (student.get('college') if student else ev.get('college') or ""),
            "class_code": student_class or class_code or "",
            "score": ev.get('score'),
            "max_score": ev.get('max_score'),
            "feedback": ev.get('feedback') or ev.get('notes') or "",
            "ai_generated": ev.get('ai_generated'),
            "evaluator": ev.get('evaluated_by') or ev.get('evaluator') or ""
        }
        rows.append(row)

    if not rows:
        print("No submissions matched filters. Creating empty sheet with headers.")
        df = pd.DataFrame(columns=[
            "assignment_id","submission_id","submission_time","student_id","student_name","student_email",
            "college","class_code","score","max_score","feedback","ai_generated","evaluator"
        ])
    else:
        df = pd.DataFrame(rows)

    print(f"Writing Excel to {output_path} ...")
    df.to_excel(output_path, index=False, engine='openpyxl')
    print("Excel created. Rows:", len(df))

    if upload_to_s3:
        if not s3_bucket:
            raise ValueError("s3_bucket must be set in config to upload.")
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        key = os.path.basename(output_path)
        print(f"Uploading {output_path} -> s3://{s3_bucket}/{key}")
        s3_client.upload_file(output_path, s3_bucket, key)
        print("Upload complete.")
    return output_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml", help="path to config yaml")
    parser.add_argument("--assignment-id", required=True)
    parser.add_argument("--class-code", default=None)
    parser.add_argument("--deadline", default=None, help="ISO datetime, e.g. 2025-09-05T23:59:59")
    parser.add_argument("--output", default=None, help="explicit output path")
    parser.add_argument("--upload-s3", action="store_true", help="upload to s3 (requires s3_bucket in config)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    dynamodb = init_dynamodb(AWS_REGION)
    output = generate_report(dynamodb, cfg, args.assignment_id, args.class_code, args.deadline, args.output, args.upload_s3)
    print("Done. Report saved at:", output)

if __name__ == "__main__":
    main()
