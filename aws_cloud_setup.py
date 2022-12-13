from operator import itemgetter
from config import settings
import datetime
import boto3
from botocore.exceptions import ClientError

aws_region = str(settings.aws_region)
ami_id = str(settings.ami_id)
min_instances = str(settings.min_count)
max_instances = str(settings.max_count)
instance_type = str(settings.instance_type)
key_name = str(settings.key_name)

security_params = {'aws_access_key_id': settings.ACCESS_KEY, 'aws_secret_access_key': settings.SECRET_KEY}
#python dict here used to contain key ID and the access key these paramateres were taken from IAM user


def get_boto_client(service_name):

    client = boto3.client(service_name, **security_params, region_name=aws_region)

    return client

#Low level implementation of boto3 that gives functionalitities to access(reach) for AWS services


def get_boto_resource(service_name):

    resource = boto3.resource(service_name, **security_params, region_name=aws_region)

    return resource

#High Level implementation

def get_all_running_ec2_resource(secure_policy):

    def fill_running_instance_list():

        ec2_resource = boto3.resource('ec2', **security_params, region_name=aws_region)

        filters_by = [
            {
                'Name': 'instance-state-name',
                'Values': ['running', 'pending']
            }
        ]

        filtered_list = ec2_resource.instances.filter(Filters=filters_by)
        #object method and another method. Second method is a special method

        for ec2_instance in filtered_list:
            list_of_running_ec2_ids.append(ec2_instance.id)
            #checking running instances

    list_of_running_ec2_ids = []

    fill_running_instance_list()

    if not list_of_running_ec2_ids:

        instance_names = list(settings.instance_names)

        for index, server_name in enumerate(instance_names):

            ec2_client.run_instances(

                    ImageId=str(settings.ami_id),
                    MinCount=int(settings.min_count),
                    MaxCount=int(settings.max_count),
                    InstanceType=str(settings.instance_type),
                    KeyName=str(settings.key_name),
                    SecurityGroupIds=[
                        secure_policy,
                    ],
                    TagSpecifications=[
                        {
                            'ResourceType': 'instance',
                            'Tags': [{'Key': f'Server', 'Value': server_name}]
                        },
                    ]
            )
#we create running instances
        fill_running_instance_list()

    return list_of_running_ec2_ids


def create_security_policy(res):

    vpc_id = res.get('Vpcs', [{}])[0].get('VpcId', '')

    try:
        response = ec2_client.create_security_group(
            GroupName='demo123',
            Description='demo_description',
            VpcId=vpc_id
        )
        security_group_id = response['GroupId']
        print('Security Group Created %s in vpc %s.' % (security_group_id, vpc_id))

        data = ec2_client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {'IpProtocol': 'tcp',
                 'FromPort': 80,
                 'ToPort': 80,
                 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp',
                 'FromPort': 22,
                 'ToPort': 22,
                 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ])
        print('Security rule Successfully Set %s' % data)

        return security_group_id

    except ClientError as e:
        print(e)


ec2_res = get_boto_resource('ec2')

ec2_client = get_boto_client('ec2')

vpc_info = ec2_client.describe_vpcs()

security_policy_id = create_security_policy(vpc_info)

cloud_watch_client = get_boto_client('cloudwatch')
ses_client = get_boto_client('ses')

temp_list = get_all_running_ec2_resource(security_policy_id)
end = datetime.datetime.utcnow()
start = end - datetime.timedelta(hours=24)

for i, ec2_id in enumerate(temp_list):

    tags_info_list = ec2_res.Instance(ec2_id).tags

    filtered_tag_list = list(filter(lambda person: person['Key'] == 'Server', tags_info_list))

    server_name = filtered_tag_list[0]['Value']

    if server_name in ['Amber', 'Red']:
        ec2_client.monitor_instances(InstanceIds=[ec2_id])

    utilization_info = cloud_watch_client.get_metric_statistics(

        Namespace='AWS/EC2',
        MetricName='CPUUtilization',
        Dimensions=[{'Name': 'InstanceId', 'Value': ec2_id}],
        StartTime=start,
        EndTime=end,
        Period=60,
        Statistics=['Average'])

    datapoints = utilization_info['Datapoints']

    print(datapoints)

    if datapoints:

        last_datapoint = sorted(datapoints, key=itemgetter('Timestamp'))[-1]
        utilization = last_datapoint['Average']
        load = round((utilization / 100.0), 3)
        timestamp = str(last_datapoint['Timestamp'])
        print("{0} load at {1}".format(load, timestamp))

        alert_amber = server_name == "Amber" and load > 50
        alert_red = server_name == "Red" and load > 80

        if alert_amber:
            InstanceID = ec2_id

            alert_response = ses_client.send_email(
                Destination={
                    'ToAddresses': [
                        'awskid001@gmail.com'
                    ],
                },
                Message={
                    'Body': {
                        'Html': {
                            'Charset': 'UTF-8',
                            'Data': '<h1>WARNING....Hello Guys!!</h1>'
                                    '<p>'
                                    f"CPU Utilization more than 50% on Amber server with InstanceID {InstanceID} ... "
                                    f"& with a {load} load at {timestamp} (UTC time)"
                                    '</p>',
                        },
                        'Text': {
                            'Charset': 'UTF-8',
                            'Data': f"CPU Utilization more than 50% on Amber server with InstanceID {InstanceID} ... "
                                    f"& with a {load} load at {timestamp} (UTC time)"
                        },
                    },
                    'Subject': {
                        'Charset': 'UTF-8',
                        'Data': 'WARNING',
                    },
                },
                Source='awskid001@gmail.com',
            )

            print("sent email for Amber Stakeholders")

        if alert_red:
            InstanceID = ec2_id

            alert_response = ses_client.send_email(
                Destination={
                    'ToAddresses': [
                        'awskid001@gmail.com'
                    ],
                },
                Message={
                    'Body': {
                        'Html': {
                            'Charset': 'UTF-8',
                            'Data': '<h1>WARNING....Hello Guys!!</h1>'
                                    '<p>'
                                    f"CPU Utilization more than 80% on Red server with InstanceID {InstanceID} ... "
                                    f"& with a {load} load at {timestamp} (UTC time)"
                                    '</p>',
                        },
                        'Text': {
                            'Charset': 'UTF-8',
                            'Data': f"CPU Utilization more than 80% on Red server with InstanceID {InstanceID} ... "
                                    f"& with a {load} load at {timestamp} (UTC time)"
                        },
                    },
                    'Subject': {
                        'Charset': 'UTF-8',
                        'Data': 'WARNING',
                    },
                },
                Source='awskid001@gmail.com',
            )

            print("sent email for Red Stakeholders")

