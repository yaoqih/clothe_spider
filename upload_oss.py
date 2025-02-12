# -*- coding: utf-8 -*-
import os
os.environ['OSS_ACCESS_KEY_ID'] = ''
os.environ['OSS_ACCESS_KEY_SECRET'] = ''
import oss2
from oss2.credentials import EnvironmentVariableCredentialsProvider
# 设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
# 从环境变量中获取访问凭证。运行本代码示例之前，请确保已设置环境变量OSS_ACCESS_KEY_ID和OSS_ACCESS_KEY_SECRET。
auth = oss2.ProviderAuth(EnvironmentVariableCredentialsProvider())
# 填写Bucket所在地域对应的Endpoint。以华东1（杭州）为例，Endpoint填写为https://oss-cn-hangzhou.aliyuncs.com。
service = oss2.Service(auth, 'https://oss-cn-hangzhou.aliyuncs.com')

# 列举当前账号所有地域下的存储空间。
for b in oss2.BucketIterator(service):
    print(b.name)