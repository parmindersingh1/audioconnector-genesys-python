class SecretService:
    """
    Provides authentication process for retrieving secrets for a given key.
    
    This is a placeholder implementation using a static map.
    In a real-world scenario, this would be replaced with a secure secrets management system.
    """
    _secrets = {
        'ApiKey1': 'Secret1',
        'ApiKey2': 'gx_4k8n2m9p6r3s7t1v5w8x2y4z6a9b3c7d1e5f8g2h6i0j4k7l1m9n3o6p2q8r5s1t7u4v0w6x9y3z8'
    }

    def get_secret_for_key(self, key: str) -> bytes:
        """
        Retrieve the secret for a given key
        
        Args:
            key: The API key to retrieve the secret for
        
        Returns:
            Secret as bytes, or empty bytes if no secret found
        """
        secret_string = self._secrets.get(key, '')
        print("000000000")
        print(key)
        print(secret_string)
    
        return secret_string.encode('utf-8')

    def get_key_for_secret(self, secret: str) -> bytes:
        for k, v in self._secrets.items():
            if v == secret:
                return k.encode('utf-8')
        return b''