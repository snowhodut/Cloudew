import boto3
import json
import base64
from typing import Dict, Optional
from functools import lru_cache


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

    def get_api_keys(self, user_id: str) -> Dict[str, str]:
        """DynamoDB에서 암호화된 API 키들을 가져와 복호화"""
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


# 전역 인스턴스 (필요시 사용)
_key_manager = None

def get_api_key_manager(session: boto3.Session, table_name: str, kms_key_id: str) -> APIKeyManager:
    global _key_manager
    if _key_manager is None or _key_manager.session != session:
        _key_manager = APIKeyManager(session, table_name, kms_key_id)
    return _key_manager
