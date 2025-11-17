class SecretService:
    """
    Provides authentication process for retrieving secrets for a given key.
    
    This is a placeholder implementation using a static map.
    In a real-world scenario, this would be replaced with a secure secrets management system.
    """
    _secrets = {
        'ApiKey1': 'Secret1',
        'ApiKey2': '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8'
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