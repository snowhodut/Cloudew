import boto3
import json
import base64
import os
from typing import Dict, Optional
from functools import lru_cache
import time


class APIKeyManager:
    def __init__(self, session: boto3.Session, table_name: str, kms_key_id: str):
        self.session = session
        self.table_name = table_name
        self.kms_key_id = kms_key_id
        self.dynamodb = session.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        self.kms = session.client('kms')

    def encrypt_api_key(self, plain_key: str) -> str:
        """API 키를 KMS로 암호화"""
        response = self.kms.encrypt(
            KeyId=self.kms_key_id,
            Plaintext=plain_key.encode('utf-8')
        )
        return base64.b64encode(response['CiphertextBlob']).decode('utf-8')

    def decrypt_api_key(self, encrypted_key: str) -> str:
        """암호화된 API 키를 복호화"""
        ciphertext_blob = base64.b64decode(encrypted_key)
        response = self.kms.decrypt(
            CiphertextBlob=ciphertext_blob
        )
        return response['Plaintext'].decode('utf-8')

    def save_api_keys(self, user_id: str, api_keys: Dict[str, str]):
        """API 키들을 암호화하여 DynamoDB에 저장"""
        encrypted_keys = {}
        for key_name, plain_key in api_keys.items():
            if plain_key:  # 빈 키는 저장하지 않음
                encrypted_keys[key_name] = self.encrypt_api_key(plain_key)

        self.table.put_item(
            Item={
                'user_id': user_id,
                'api_keys': encrypted_keys
            }
        )

    @lru_cache(maxsize=100)  # 캐시 추가로 성능 향상
    def get_api_keys(self, user_id: str) -> Dict[str, str]:
        """DynamoDB에서 암호화된 API 키들을 가져와 복호화 (캐시 적용)"""
        response = self.table.get_item(Key={'user_id': user_id})
        if 'Item' not in response:
            return {}

        encrypted_keys = response['Item'].get('api_keys', {})
        decrypted_keys = {}
        for key_name, encrypted_key in encrypted_keys.items():
            try:
                decrypted_keys[key_name] = self.decrypt_api_key(encrypted_key)
            except Exception as e:
                print(f"Failed to decrypt {key_name}: {e}")
                decrypted_keys[key_name] = ""

        return decrypted_keys

    def get_api_key(self, user_id: str, key_name: str) -> Optional[str]:
        """특정 API 키만 가져오기"""
        keys = self.get_api_keys(user_id)
        return keys.get(key_name)


# Lambda용 헬퍼 함수
@lru_cache(maxsize=50)  # Lambda 컨테이너 재사용을 위한 캐시
def get_api_key_manager_for_lambda():
    """Lambda 환경에서 사용할 API 키 매니저 (캐시 적용)"""
    session = boto3.Session()
    table_name = os.environ.get('USER_CONFIG_TABLE', 'UserConfigTable')
    kms_key_id = os.environ.get('KMS_KEY_ID', 'alias/guardduty-project-key')
    return APIKeyManager(session, table_name, kms_key_id)


@lru_cache(maxsize=200)  # 개별 키 캐시
def get_api_key_for_lambda(user_id: str, key_name: str) -> Optional[str]:
    """Lambda에서 특정 API 키 가져오기 (캐시 적용)"""
    manager = get_api_key_manager_for_lambda()
    return manager.get_api_key(user_id, key_name)