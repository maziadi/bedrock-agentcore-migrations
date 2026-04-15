import * as cdk from 'aws-cdk-lib';
import { IpponAssistantStack } from '../lib/stack';

const app = new cdk.App();

new IpponAssistantStack(app, 'IpponAssistantStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'us-east-1',
  },
});
