import boto3
import base64
import os
from botocore.exceptions import ClientError

# CDK로 생성한 KMS Key ID (환경변수로 주입하거나 config에서 관리)
KMS_KEY_ID = os.getenv("KMS_KEY_ID", "alias/guardduty-project-key")


class SecurityManager:
    def __init__(self):
        self.kms = boto3.client("kms", region_name="ap-northeast-2")

    def decrypt_api_key(self, encrypted_key_b64: str) -> str:
        """
        [Lambda/EC2 내부용] DB에 저장된 암호화 키를 복호화하여 평문으로 반환
        Claude API 호출 직전에 사용
        """
        try:
            # 1. Base64 디코딩
            ciphertext = base64.b64decode(encrypted_key_b64)

            # 2. KMS 복호화
            response = self.kms.decrypt(CiphertextBlob=ciphertext, KeyId=KMS_KEY_ID)

            # 3. 평문 반환
            return response["Plaintext"].decode("utf-8")
        except ClientError as e:
            print(f"Decryption failed: {e}")
            raise e

    def encrypt_api_key(self, plaintext_key: str) -> str:
        """
        [Streamlit 저장용] 사용자가 입력한 키를 암호화하여 DB 저장용 문자열 반환
        """
        try:
            response = self.kms.encrypt(
                KeyId=KMS_KEY_ID, Plaintext=plaintext_key.encode("utf-8")
            )
            # Base64 인코딩하여 저장
            return base64.b64encode(response["CiphertextBlob"]).decode("utf-8")
        except ClientError as e:
            print(f"Encryption failed: {e}")
            raise e
